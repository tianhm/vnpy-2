# encoding: UTF-8

'''
This file contains backtesting engine for CTA module, the API of backtesing engine is the same as CTA engine.
Trading code can be directly used to backtest.
'''

from __future__ import division

from datetime import datetime, timedelta
from collections import OrderedDict
from itertools import product
import multiprocessing
import pymongo

from ctaBase import *
from ctaSetting import *

from vtConstant import *
from vtGateway import VtOrderData, VtTradeData
from vtFunction import loadMongoSetting


########################################################################
class BacktestingEngine(object):
    """
    CTA backtest engine
    Function interface is designed to be the same as CTA engine, which allow using the same code to do both
    trading and backtesting tasks.
    """
    
    TICK_MODE = 'tick'
    BAR_MODE = 'bar'

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""

        # Count local stop orders
        self.stopOrderCount = 0
        # stopOrderID = STOPORDERPREFIX + str(stopOrderCount)
        
        # Dictionary: local stop orders
        # key: stopOrderID; value: stopOrder

        # Whenever a stop order has been cancelled, it is not removed from this dictionary.
        self.stopOrderDict = {}

        # Once a stop order has been cancelled, it is removed from this dictionary.
        self.workingStopOrderDict = {}
        
        # Set engine type as "backtest"
        self.engineType = ENGINETYPE_BACKTESTING
        
        # Backtest variables setting
        self.strategy = None        # define strategy variable
        self.mode = self.BAR_MODE   # define backtest mode, set "bar" as default
        
        self.startDate = ''
        self.initDays = 0           # The data used to initialise strategy (not calculate)
        self.endDate = ''

        self.slippage = 0           # set slippage
        self.rate = 0               # set commission (percentage rate)
        self.size = 1               # position size, set "1" as default
        
        self.dbClient = None        # Database Client
        self.dbCursor = None        # Databse cursor

        self.initData = []          # The data used to initialise strategy
        
        self.dbName = ''            # Name of database for backtesting
        self.symbol = ''            # Name of symbol
        
        self.dataStartDate = None       # Backtest starting date, in "datetime" format
        self.dataEndDate = None         # Backtest starting date, in "datetime" format

        # Strategy starting date (data before this date is for initialization only), in "datetime" format
        self.strategyStartDate = None

        # OrderedDict is a dictionary that is forced to follow a specific order
        self.limitOrderDict = OrderedDict()         # dictionary of limit order

        # Dictionary of working limit order
        self.workingLimitOrderDict = OrderedDict()
        self.limitOrderCount = 0                    # Limit order's number
        
        self.tradeCount = 0             # Trade's number
        self.tradeDict = OrderedDict()  # Dictionary of trades
        
        self.logList = []               # Log
        
        # The latest data
        self.tick = None
        self.bar = None
        self.dt = None      # The latest time stamp, in "datetime" format
        
    #----------------------------------------------------------------------
    def setStartDate(self, startDate='20100416', initDays=10):
        """set start date"""

        self.startDate = startDate
        self.initDays = initDays
        
        self.dataStartDate = datetime.strptime(startDate, '%Y%m%d')
        
        initTimeDelta = timedelta(initDays)

        # the real start date = start date + initial days
        self.strategyStartDate = self.dataStartDate + initTimeDelta
        
    #----------------------------------------------------------------------
    def setEndDate(self, endDate=''):
        """set end date"""

        self.endDate = endDate
        if endDate:
            self.dataEndDate= datetime.strptime(endDate, '%Y%m%d')
            # To include the data at the day "dataEndDate"
            self.dataEndDate.replace(hour=23, minute=59)    
        
    #----------------------------------------------------------------------
    def setBacktestingMode(self, mode):
        """set backtest mode"""

        # "Bar" or "Tick"
        self.mode = mode
    
    #----------------------------------------------------------------------
    def setDatabase(self, dbType, dbName, symbol):
        """set database that provide historical data"""

        self.dbType      = dbType
        self.dbName      = dbName
        self.symbol      = symbol
    
    #----------------------------------------------------------------------
    def loadHistoryData(self):
        """load historical data"""

        if self.dbType == "MongoDB":

            host, port = loadMongoSetting()

            self.dbClient = pymongo.MongoClient(host, port)
            collection = self.dbClient[self.dbName][self.symbol]

            self.output("Start loading historical data from MongoDB")

            # Choose data type based on backtest mode
            if self.mode == self.BAR_MODE:
                dataClass = CtaBarData
            else:
                dataClass = CtaTickData

            # Load initialised data

            # $gte means "greater and equal to"
            # $lt means "less than"
            flt = {'datetime':{'$gte':self.dataStartDate,
                               '$lt':self.strategyStartDate}}
            initCursor = collection.find(flt)

            # Read data from cursor, generate a list
            self.initData = []                                      # Empty "initData" list
            for d in initCursor:
                data = dataClass()
                data.__dict__ = d
                self.initData.append(data)

            # Load backtest data (exclude initialised data)
            if not self.dataEndDate:

                # If "End Date" is not set, retreat data up to today
                flt = {'datetime':{'$gte':self.strategyStartDate}}
            else:
                flt = {'datetime':{'$gte':self.strategyStartDate,
                                   '$lte':self.dataEndDate}}
            self.dbCursor = collection.find(flt)

            self.output("Data loading complete, data volumn: %s" %(initCursor.count() + self.dbCursor.count()))

        elif self.dbType == "SQLite":

            import sqlite3 as sq

            DBpath = "Z:\9Data\\1SQL_Database\%s" % (self.dbName) + ".db"
            self.output("Start loading historical data from SQLite")

            def dict_factory(cursor, row):
                d = {}
                for idx, col in enumerate(cursor.description):
                    new_name = col[0].lower()
                    d[new_name] = row[idx]

                    # if new_name == "datetime":
                    #     new_date = datetime.strptime(row[idx], '%Y-%m-%d %H:%M:%S')
                    #     d[new_name] = new_date
                    # else:
                    #     d[new_name] = row[idx]

                return d

            conn = sq.connect(DBpath)
            conn.row_factory = dict_factory
            db = conn.cursor()

            # Choose data type based on backtest mode
            if self.mode == self.BAR_MODE:
                dataClass = CtaBarData
            else:
                dataClass = CtaTickData

            # Load initialization data

            initCursor = db.execute("""
            SELECT * FROM '%s' WHERE (DateTime >= '%s' and DateTime < '%s')
            """ % (self.symbol, self.dataStartDate, self.strategyStartDate)).fetchall()

            # Read data from cursor, generate a list
            self.initData = []  # Empty "initData" list
            for d in initCursor:
                data = dataClass()
                data.__dict__ = d
                self.initData.append(data)

            # Load backtest data (exclude initialised data)
            if not self.dataEndDate:

                # If "End Date" is not set, retreat data up to today
                self.dbCursor = db.execute("""
                    SELECT * FROM '%s' WHERE DateTime >= '%s'
                    """ % (self.symbol, self.strategyStartDate,)).fetchall()

            else:

                self.dbCursor = db.execute("""
                    SELECT * FROM '%s' WHERE (DateTime >= '%s' and DateTime < '%s')
                    """ % (self.symbol, self.strategyStartDate, self.dataEndDate)).fetchall()

            self.output("Data loading complete, data volumn: %s" % (len(initCursor) + len(self.dbCursor)))
        
    #----------------------------------------------------------------------
    def runBacktesting(self):
        """Run backtesting"""

        # Load historical data
        self.loadHistoryData()

        # First, choose data class and data update function (Bar or Tick) based on backtest mode
        if self.mode == self.BAR_MODE:
            dataClass = CtaBarData
            func = self.newBar
        else:
            dataClass = CtaTickData
            func = self.newTick

        self.output("Start backtesing!")
        
        self.strategy.inited = True
        self.strategy.onInit()
        self.output("Strategy initialsing complete")
        
        self.strategy.trading = True
        self.strategy.onStart()
        self.output("Strategy started")
        
        self.output("Processing historical data...")

        for d in self.dbCursor:
            data = dataClass()
            data.__dict__ = d
            func(data)     
            
        self.output("No more historical data")
        
    #----------------------------------------------------------------------
    def updatePosition(self):
        """Update position information"""
        pass

    #----------------------------------------------------------------------
    def newBar(self, bar):
        """new ohlc Bar"""

        self.bar = bar
        self.dt = bar.datetime
        self.updatePosition()       # Update total position value based on new Bar
        self.crossLimitOrder()      # Check any limit order is triggered
        self.crossStopOrder()       # Check any stop order is triggered
        self.strategy.onBar(bar)    # Push data (Bar) to strategy
    
    #----------------------------------------------------------------------
    def newTick(self, tick):
        """new Tick"""

        self.tick = tick
        self.dt = tick.datetime
        self.updatePosition()
        self.crossLimitOrder()
        self.crossStopOrder()
        self.strategy.onTick(tick)
        
    #----------------------------------------------------------------------
    def initStrategy(self, strategyClass, setting=None):
        """
        Initializing Strategy
        'setting' is the configuration of strategy, if default setting is adopted, no need to pass this parameter.
        """
        self.strategy = strategyClass(self, setting)
        self.strategy.name = self.strategy.className
        
    #----------------------------------------------------------------------
    def sendOrder(self, vtSymbol, orderType, price, volume, strategy):
        """send order"""

        self.limitOrderCount += 1
        orderID = str(self.limitOrderCount)
        
        order = VtOrderData()
        order.vtSymbol = vtSymbol
        order.price = price
        order.totalVolume = volume
        order.status = STATUS_NOTTRADED         # the status of new limit order is not traded
        order.orderID = orderID
        order.vtOrderID = orderID
        order.orderTime = str(self.dt)
        
        # CTA order type
        if orderType == CTAORDER_BUY:
            order.direction = DIRECTION_LONG
            order.offset = OFFSET_OPEN
        elif orderType == CTAORDER_SELL:
            order.direction = DIRECTION_SHORT
            order.offset = OFFSET_CLOSE
        elif orderType == CTAORDER_SHORT:
            order.direction = DIRECTION_SHORT
            order.offset = OFFSET_OPEN
        elif orderType == CTAORDER_COVER:
            order.direction = DIRECTION_LONG
            order.offset = OFFSET_CLOSE     
        
        # Put this Limit Order into "limit order dictionary" and "working limit order dictionary"
        self.workingLimitOrderDict[orderID] = order
        self.limitOrderDict[orderID] = order
        
        return orderID
    
    #----------------------------------------------------------------------
    def cancelOrder(self, vtOrderID):
        """cancel order"""

        if vtOrderID in self.workingLimitOrderDict:
            order = self.workingLimitOrderDict[vtOrderID]
            order.status = STATUS_CANCELLED
            order.cancelTime = str(self.dt)
            del self.workingLimitOrderDict[vtOrderID]
        
    #----------------------------------------------------------------------
    def sendStopOrder(self, vtSymbol, orderType, price, volume, strategy):
        """send StopOrder"""

        self.stopOrderCount += 1
        stopOrderID = STOPORDERPREFIX + str(self.stopOrderCount)
        
        so = StopOrder()
        so.vtSymbol = vtSymbol
        so.price = price
        so.volume = volume
        so.strategy = strategy
        so.stopOrderID = stopOrderID
        so.status = STOPORDER_WAITING
        
        if orderType == CTAORDER_BUY:
            so.direction = DIRECTION_LONG
            so.offset = OFFSET_OPEN
        elif orderType == CTAORDER_SELL:
            so.direction = DIRECTION_SHORT
            so.offset = OFFSET_CLOSE
        elif orderType == CTAORDER_SHORT:
            so.direction = DIRECTION_SHORT
            so.offset = OFFSET_OPEN
        elif orderType == CTAORDER_COVER:
            so.direction = DIRECTION_LONG
            so.offset = OFFSET_CLOSE           
        
        # Put this Stop Order into "stop order dictionary" and "working stop order dictionary"
        self.stopOrderDict[stopOrderID] = so
        self.workingStopOrderDict[stopOrderID] = so
        
        return stopOrderID
    
    #----------------------------------------------------------------------
    def cancelStopOrder(self, stopOrderID):
        """cancel StopOrder"""

        # Check whether this StopOrder exists
        if stopOrderID in self.workingStopOrderDict:
            so = self.workingStopOrderDict[stopOrderID]
            so.status = STOPORDER_CANCELLED
            del self.workingStopOrderDict[stopOrderID]
            
    #----------------------------------------------------------------------
    def crossLimitOrder(self):
        """Check LimitOrder based on the latest market data"""

        # Define trigger prices, "bar mode" and "tick mode" are different.
        if self.mode == self.BAR_MODE:

            # If "low" is lower than order price, then buy
            buyCrossPrice = self.bar.low
            # If "high" is higher than order price, then sell
            sellCrossPrice = self.bar.high
            buyBestCrossPrice = self.bar.open
            sellBestCrossPrice = self.bar.open
        else:
            buyCrossPrice = self.tick.askPrice1
            sellCrossPrice = self.tick.bidPrice1
            buyBestCrossPrice = self.tick.askPrice1
            sellBestCrossPrice = self.tick.bidPrice1
        
        # Loop through all the limit order in "workingLimitOrderDict"
        for orderID, order in self.workingLimitOrderDict.items():
            # Whether to trade or not

            # If "low" is lower than order price and the direction is "long", then this order is triggered
            buyCross = order.direction==DIRECTION_LONG and order.price>=buyCrossPrice
            # If "high" is higher than order price and the direction is "short", then this order is triggered
            sellCross = order.direction==DIRECTION_SHORT and order.price<=sellCrossPrice

            # If trades
            if buyCross or sellCross:
                # Update trade data
                self.tradeCount += 1            # TradeID increase by 1
                tradeID = str(self.tradeCount)
                trade = VtTradeData()
                trade.vtSymbol = order.vtSymbol
                trade.tradeID = tradeID
                trade.vtTradeID = tradeID
                trade.orderID = order.orderID
                trade.vtOrderID = order.orderID
                trade.direction = order.direction
                trade.offset = order.offset
                
                # Buy as example:
                # 1. Suppose the OHLC of current Bar are 100, 125, 90, 110 (Open = 100)
                # 2. Suppose at the end of last Bar (not the start of current Bar), the price of limit order is 105,
                #    (Last Close = 105)
                # 3. Actually, the trade price will be 100 instead of 105, because the best market price is 100
                if buyCross:
                    trade.price = min(order.price, buyBestCrossPrice)
                    self.strategy.pos += order.totalVolume
                else:
                    trade.price = max(order.price, sellBestCrossPrice)
                    self.strategy.pos -= order.totalVolume
                
                trade.volume = order.totalVolume
                trade.tradeTime = str(self.dt)
                trade.dt = self.dt
                self.strategy.onTrade(trade)
                
                self.tradeDict[tradeID] = trade

                # Upadte order data
                order.tradedVolume = order.totalVolume
                order.status = STATUS_ALLTRADED
                self.strategy.onOrder(order)

                # Remove this order from "workingLimitOrderDict"
                del self.workingLimitOrderDict[orderID]
                
    #----------------------------------------------------------------------
    def crossStopOrder(self):
        """Check StopOrder based on the latest market data"""

        # Define trigger price, the rule is contrary to limit order
        if self.mode == self.BAR_MODE:
            buyCrossPrice = self.bar.high
            sellCrossPrice = self.bar.low
            bestCrossPrice = self.bar.open
        else:
            buyCrossPrice = self.tick.lastPrice
            sellCrossPrice = self.tick.lastPrice
            bestCrossPrice = self.tick.lastPrice

        # Loop through all the stop order in "workingStopOrderDict"
        for stopOrderID, so in self.workingStopOrderDict.items():
            # Whether to trade or not
            buyCross = so.direction==DIRECTION_LONG and so.price<=buyCrossPrice
            sellCross = so.direction==DIRECTION_SHORT and so.price>=sellCrossPrice

            # If trades
            if buyCross or sellCross:
                # Update trade data
                self.tradeCount += 1            # TradeID increase by 1
                tradeID = str(self.tradeCount)
                trade = VtTradeData()
                trade.vtSymbol = so.vtSymbol
                trade.tradeID = tradeID
                trade.vtTradeID = tradeID
                
                if buyCross:
                    self.strategy.pos += so.volume
                    trade.price = max(bestCrossPrice, so.price)
                else:
                    self.strategy.pos -= so.volume
                    trade.price = min(bestCrossPrice, so.price)                
                
                self.limitOrderCount += 1
                orderID = str(self.limitOrderCount)
                trade.orderID = orderID
                trade.vtOrderID = orderID
                
                trade.direction = so.direction
                trade.offset = so.offset
                trade.volume = so.volume
                trade.tradeTime = str(self.dt)
                trade.dt = self.dt
                self.strategy.onTrade(trade)
                
                self.tradeDict[tradeID] = trade

                # Upadte order data
                so.status = STOPORDER_TRIGGERED
                
                order = VtOrderData()
                order.vtSymbol = so.vtSymbol
                order.symbol = so.vtSymbol
                order.orderID = orderID
                order.vtOrderID = orderID
                order.direction = so.direction
                order.offset = so.offset
                order.price = so.price
                order.totalVolume = so.volume
                order.tradedVolume = so.volume
                order.status = STATUS_ALLTRADED
                order.orderTime = trade.tradeTime
                self.strategy.onOrder(order)
                
                self.limitOrderDict[orderID] = order

                # Remove this order from "workingStopOrderDict"
                del self.workingStopOrderDict[stopOrderID]        

    #----------------------------------------------------------------------
    def insertData(self, dbName, collectionName, data):
        """Ban this functionality in backtesting mode"""
        pass
    
    #----------------------------------------------------------------------
    def loadBar(self, dbName, collectionName, startDate):
        """Return bar in initialization data"""
        return self.initData
    
    #----------------------------------------------------------------------
    def loadTick(self, dbName, collectionName, startDate):
        """Return tick in initialization data"""
        return self.initData
    
    #----------------------------------------------------------------------
    def writeCtaLog(self, content):
        """Record Log"""
        log = str(self.dt) + ' ' + content 
        self.logList.append(log)
        
    #----------------------------------------------------------------------
    def output(self, content):
        """Output content"""
        print str(datetime.now()) + "\t" + content 
    
    #----------------------------------------------------------------------
    def calculateBacktestingResult(self):
        """
        Calculate backtesting result
        """

        self.output("Calculating backtesting result")

        # First, based on trade lists, calculate profit/loss for each trade

        resultList = []             # Record result of trades
        
        longTrade = []              # Record long trades that haven't been closed
        shortTrade = []             # Record short trades that haven't been closed

        for trade in self.tradeDict.values():

            # Long Trades
            if trade.direction == DIRECTION_LONG:

                # If no short position holds
                if not shortTrade:
                    longTrade.append(trade)

                # If exists short position, this long trade is a close trade
                else:
                    while True:
                        entryTrade = shortTrade[0]
                        exitTrade = trade

                        # Calculate close trade
                        closedVolume = min(exitTrade.volume, entryTrade.volume)
                        result = TradingResult(entryTrade.price, entryTrade.dt, 
                                               exitTrade.price, exitTrade.dt,
                                               -closedVolume, self.rate, self.slippage, self.size)
                        resultList.append(result)

                        # Calculate the remaining position
                        entryTrade.volume -= closedVolume
                        exitTrade.volume -= closedVolume

                        # If no remaining position for entry trade, remove this trade from "shortTrade" list
                        if not entryTrade.volume:
                            shortTrade.pop(0)

                        # If no remaining position for exit trade, exits this loop
                        if not exitTrade.volume:
                            break

                        # If exit trade has remaining position
                        if exitTrade.volume:
                            # If entry trade is cleared
                            # the remaining part of exit trade equals to a long trade
                            if not shortTrade:
                                longTrade.append(exitTrade)
                                break
                            # If entry trade is not cleared, goes to next iteration
                            else:
                                pass

            # Short trades
            else:

                # If no long position holds
                if not longTrade:
                    shortTrade.append(trade)

                # If exists long position
                else:                    
                    while True:
                        entryTrade = longTrade[0]
                        exitTrade = trade

                        # Calculate close trade
                        closedVolume = min(exitTrade.volume, entryTrade.volume)
                        result = TradingResult(entryTrade.price, entryTrade.dt, 
                                               exitTrade.price, exitTrade.dt,
                                               closedVolume, self.rate, self.slippage, self.size)
                        resultList.append(result)
                        
                        # Calculate the remaining position
                        entryTrade.volume -= closedVolume
                        exitTrade.volume -= closedVolume
                        
                        # If no remaining position for entry trade, remove this trade from "longTrade" list
                        if not entryTrade.volume:
                            longTrade.pop(0)
                        
                        # If no remaining position for exit trade, exits this loop
                        if not exitTrade.volume:
                            break
                        
                        # If exit trade has remaining position
                        if exitTrade.volume:
                            # If entry trade is cleared
                            # the remaining part of exit trade equals to a long trade
                            if not longTrade:
                                shortTrade.append(exitTrade)
                                break

                            # If entry trade is not cleared, goes to next iteration
                            else:
                                pass                    

        # If no trade has been recorded
        if not resultList:
            self.output("No trade has been recorded")
            return {}
        
        # Based on trades results, calculate indicators, such as equity curve and maximum drawdown
        capital = 0             # Equity
        maxCapital = 0          # Maximum equity
        drawdown = 0
        
        totalResult = 0         # Number of total trades
        totalTurnover = 0
        totalCommission = 0
        totalSlippage = 0
        
        timeList = []           # Record trading time for every trades
        pnlList = []            # Record profit (or loss) for every trades
        capitalList = []        # Record equity curve
        drawdownList = []       # Record drawdown
        
        winningResult = 0       # Win trades
        losingResult = 0        # Loss trades
        totalWinning = 0        # Total win
        totalLosing = 0         # Total loss
        
        for result in resultList:
            capital += result.pnl
            maxCapital = max(capital, maxCapital)
            drawdown = capital - maxCapital
            
            pnlList.append(result.pnl)
            timeList.append(result.exitDt)      # Record exit time as trading time
            capitalList.append(capital)
            drawdownList.append(drawdown)
            
            totalResult += 1
            totalTurnover += result.turnover
            totalCommission += result.commission
            totalSlippage += result.slippage
            
            if result.pnl >= 0:
                winningResult += 1
                totalWinning += result.pnl
            else:
                losingResult += 1
                totalLosing += result.pnl
                
        # 计算盈亏相关数据
        # Calculate indicators, such as WinRatio, AveTrade, Profit Factor
        winningRate = winningResult/totalResult*100
        
        averageWinning = 0
        averageLosing = 0
        profitLossRatio = 0
        
        if winningResult:
            averageWinning = totalWinning/winningResult     # Ave win
        if losingResult:
            averageLosing = totalLosing/losingResult        # Ave loss
        if averageLosing:
            profitLossRatio = -averageWinning/averageLosing # Profit factor

        # Return results
        d = {}
        d['capital'] = capital
        d['maxCapital'] = maxCapital
        d['drawdown'] = drawdown
        d['totalResult'] = totalResult
        d['totalTurnover'] = totalTurnover
        d['totalCommission'] = totalCommission
        d['totalSlippage'] = totalSlippage
        d['timeList'] = timeList
        d['pnlList'] = pnlList
        d['capitalList'] = capitalList
        d['drawdownList'] = drawdownList
        d['winningRate'] = winningRate
        d['averageWinning'] = averageWinning
        d['averageLosing'] = averageLosing
        d['profitLossRatio'] = profitLossRatio
        
        return d
        
    #----------------------------------------------------------------------
    def showBacktestingResult(self):
        """Show backtesting result"""

        d = self.calculateBacktestingResult()

        # Output
        self.output('-' * 30)
        self.output('First Trade：\t%s' % d['timeList'][0])
        self.output('Last Trade：\t%s' % d['timeList'][-1])
        
        self.output('Total Trades：\t%s' % formatNumber(d['totalResult']))
        self.output('Total Return：\t%s' % formatNumber(d['capital']))
        self.output('Maximum Drawdown: \t%s' % formatNumber(min(d['drawdownList'])))
        
        self.output('Ave Trade：\t%s' %formatNumber(d['capital']/d['totalResult']))
        self.output('Ave Slippage：\t%s' %formatNumber(d['totalSlippage']/d['totalResult']))
        self.output('Ave Commission：\t%s' %formatNumber(d['totalCommission']/d['totalResult']))
        
        self.output('Win Ratio\t\t%s%%' %formatNumber(d['winningRate']))
        self.output('Ave Win\t%s' %formatNumber(d['averageWinning']))
        self.output('Ave Loss\t%s' %formatNumber(d['averageLosing']))
        self.output('Profit Factor：\t%s' %formatNumber(d['profitLossRatio']))
    
        # Use Bokeh to plot
        from bokeh.charts import Area, Line, Histogram
        from bokeh.layouts import column
        from bokeh.io import show

        plotdata = {"TradeN": range(len(d['capitalList'])),
                    "Equity Curve": d['capitalList'],
                    "Maximum Drawdown": d['drawdownList'],
                    "Profit/Loss": d['pnlList']}

        f1 = Line(plotdata,x="TradeN",y="Equity Curve",color="blue",width=1000,height=300)
        f2 = Area(plotdata,x="TradeN",y="Maximum Drawdown",color="tomato",width=1000,height=300)
        f3 = Histogram(plotdata,values="Profit/Loss",bins=30,color="green",width=1000,height=300)

        show(column(f1,f2,f3))
    
    #----------------------------------------------------------------------
    def putStrategyEvent(self, name):
        """Update strategy event"""
        pass

    #----------------------------------------------------------------------
    def setSlippage(self, slippage):
        """Set slippage"""
        self.slippage = slippage
        
    #----------------------------------------------------------------------
    def setSize(self, size):
        """Set contract size"""
        self.size = size
        
    #----------------------------------------------------------------------
    def setRate(self, rate):
        """Set commission ratio"""
        self.rate = rate

    #----------------------------------------------------------------------
    def runOptimization(self, strategyClass, optimizationSetting):
        """优化参数"""
        # 获取优化设置        
        settingList = optimizationSetting.generateSetting()
        targetName = optimizationSetting.optimizeTarget
        
        # 检查参数设置问题
        if not settingList or not targetName:
            self.output(u'优化设置有问题，请检查')
        
        # 遍历优化
        resultList = []
        for setting in settingList:
            self.clearBacktestingResult()
            self.output('-' * 30)
            self.output('setting: %s' %str(setting))
            self.initStrategy(strategyClass, setting)
            self.runBacktesting()
            d = self.calculateBacktestingResult()
            try:
                targetValue = d[targetName]
            except KeyError:
                targetValue = 0
            resultList.append(([str(setting)], targetValue))
        
        # 显示结果
        resultList.sort(reverse=True, key=lambda result:result[1])
        self.output('-' * 30)
        self.output(u'优化结果：')
        for result in resultList:
            self.output(u'%s: %s' %(result[0], result[1]))
        return result
            
    #----------------------------------------------------------------------
    def clearBacktestingResult(self):
        """清空之前回测的结果"""
        # 清空限价单相关
        self.limitOrderCount = 0
        self.limitOrderDict.clear()
        self.workingLimitOrderDict.clear()        
        
        # 清空停止单相关
        self.stopOrderCount = 0
        self.stopOrderDict.clear()
        self.workingStopOrderDict.clear()
        
        # 清空成交相关
        self.tradeCount = 0
        self.tradeDict.clear()
        
    #----------------------------------------------------------------------
    def runParallelOptimization(self, strategyClass, optimizationSetting):
        """并行优化参数"""
        # 获取优化设置        
        settingList = optimizationSetting.generateSetting()
        targetName = optimizationSetting.optimizeTarget
        
        # 检查参数设置问题
        if not settingList or not targetName:
            self.output(u'优化设置有问题，请检查')
        
        # 多进程优化，启动一个对应CPU核心数量的进程池
        pool = multiprocessing.Pool(multiprocessing.cpu_count())
        l = []
        for setting in settingList:
            l.append(pool.apply_async(optimize, (strategyClass, setting,
                                                 targetName, self.mode, 
                                                 self.startDate, self.initDays, self.endDate,
                                                 self.slippage, self.rate, self.size,
                                                 self.dbName, self.symbol)))
        pool.close()
        pool.join()
        
        # Show results
        resultList = [res.get() for res in l]
        resultList.sort(reverse=True, key=lambda result:result[1])
        self.output('-' * 30)
        self.output(u'优化结果：')
        for result in resultList:
            self.output(u'%s: %s' %(result[0], result[1]))    
        

########################################################################
class TradingResult(object):
    """Result of a trade (open and close)"""

    #----------------------------------------------------------------------
    def __init__(self, entryPrice, entryDt, exitPrice, 
                 exitDt, volume, rate, slippage, size):
        """Constructor"""
        self.entryPrice = entryPrice    # Entry price
        self.exitPrice = exitPrice      # Exit price
        
        self.entryDt = entryDt          # Entry time
        self.exitDt = exitDt            # Exit time
        
        self.volume = volume    # Trade volumn (+/- for direction)
        
        self.turnover = (self.entryPrice+self.exitPrice)*size*abs(volume)   # Volumn of transaction
        self.commission = self.turnover*rate                                # Commission
        self.slippage = slippage*2*size*abs(volume)                         # Slippage
        self.pnl = ((self.exitPrice - self.entryPrice) * volume * size 
                    - self.commission - self.slippage)                      # Net profit


########################################################################
class OptimizationSetting(object):
    """优化设置"""

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        self.paramDict = OrderedDict()
        
        self.optimizeTarget = ''        # 优化目标字段
        
    #----------------------------------------------------------------------
    def addParameter(self, name, start, end, step):
        """增加优化参数"""
        if end <= start:
            print u'参数起始点必须小于终止点'
            return
        
        if step <= 0:
            print u'参数布进必须大于0'
            return
        
        l = []
        param = start
        
        while param <= end:
            l.append(param)
            param += step
        
        self.paramDict[name] = l
        
    #----------------------------------------------------------------------
    def generateSetting(self):
        """生成优化参数组合"""
        # 参数名的列表
        nameList = self.paramDict.keys()
        paramList = self.paramDict.values()
        
        # 使用迭代工具生产参数对组合
        productList = list(product(*paramList))
        
        # 把参数对组合打包到一个个字典组成的列表中
        settingList = []
        for p in productList:
            d = dict(zip(nameList, p))
            settingList.append(d)
    
        return settingList
    
    #----------------------------------------------------------------------
    def setOptimizeTarget(self, target):
        """设置优化目标字段"""
        self.optimizeTarget = target


#----------------------------------------------------------------------
def formatNumber(n):
    """格式化数字到字符串"""
    rn = round(n, 2)        # 保留两位小数
    return format(rn, ',')  # 加上千分符
    

#----------------------------------------------------------------------
def optimize(strategyClass, setting, targetName,
             mode, startDate, initDays, endDate,
             slippage, rate, size,
             dbName, symbol):
    """多进程优化时跑在每个进程中运行的函数"""
    engine = BacktestingEngine()
    engine.setBacktestingMode(mode)
    engine.setStartDate(startDate, initDays)
    engine.setSlippage(slippage)
    engine.setRate(rate)
    engine.setSize(size)
    engine.setDatabase(dbName, symbol)
    
    engine.initStrategy(strategyClass, setting)
    engine.runBacktesting()
    d = engine.calculateBacktestingResult()
    try:
        targetValue = d[targetName]
    except KeyError:
        targetValue = 0            
    return (str(setting), targetValue)    


if __name__ == '__main__':

    # Following is a demo of strategy backtesting

    from ctaDemo import *

    '''
    Create backtesting engine
    Set backtest mode as "Bar"
    Set "Start Date" of data range
    Load historical data to engine
    Create strategy instance in engine
    '''
    engine = BacktestingEngine()
    engine.setBacktestingMode(engine.BAR_MODE)
    engine.setStartDate('20140101')
    engine.setDatabase("SQLite", "ZCDatabase.db", "@GC_1T")
    engine.initStrategy(DoubleEmaDemo, {})

    # Set parameters for instrument
    engine.setSlippage(0.2)
    engine.setRate(0.3/10000)
    engine.setSize(300)
    
    # Start backtesting
    engine.runBacktesting()
    
    # Show backtesting result
    engine.showBacktestingResult()