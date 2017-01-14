# encoding: UTF-8

'''
This file add multi Time Frame functionalities to CTA backtesting engine, the APIs are the
same as CTA engine. Real trading code can be directly used for backtesting.
'''

from __future__ import division
from vtFunction import loadMongoSetting

from ctaBacktesting import *

class BacktestEngineMultiTF(BacktestingEngine):

    def __init__(self):
        """Constructor"""
        super(BacktestEngineMultiTF, self).__init__()

        self.info_symbols   = []        # List, 输入辅助品种的2值tuple, 左边为数据库名, 右边为collection名
        self.InfoCursor     = {}        # Dict, 放置回测用辅助品种数据库
        self.initInfoCursor = {}        # Dict, 放置初始化用辅助品种数据库
        self.infobar        = {}        # Dict, 放置辅助品种最新一个K线数据
        self.MultiOn        = False     # Boolean, 判断是否传入了辅助品种

    # ----------------------------------------------------------------------
    def setDatabase(self, dbName, symbol, **kwargs):
        """set database that provide historical data"""

        self.dbName = dbName

        # Set executed symbol and information symbols
        self.symbol = symbol
        if "info_symbol" in kwargs:
            self.info_symbols = kwargs["info_symbol"]

            # Turn on MultiTF switch
            if len(self.info_symbols) > 0:
                self.MultiOn = True

    # ----------------------------------------------------------------------
    def loadInitData(self, collection, **kwargs):
        """Load initializing data"""

        # Load initialization data

        # $gte means "greater and equal to"
        # $lt means "less than"
        flt = {'datetime': {'$gte': self.dataStartDate,
                            '$lt': self.strategyStartDate}}
        self.initCursor = collection.find(flt)

        # Initializing information data
        if "inf" in kwargs:
            for name in kwargs["inf"]:
                DB = kwargs["inf"][name]
                self.initInfoCursor[name] = DB.find(flt)

        # Read data from cursor, generate a list
        self.initData = []

        for d in self.initCursor:
            data = self.dataClass()
            data.__dict__ = d
            self.initData.append(data)

    # ----------------------------------------------------------------------
    def loadHistoryData(self):

        """load historical data"""

        host, port = loadMongoSetting()

        self.dbClient = pymongo.MongoClient(host, port)
        collection = self.dbClient[self.dbName][self.symbol]

        # Load historical data of information symbols, construct a dictionary of Database
        # The values of dictionary are MongoDB.Client.
        info_collection = {}
        if self.MultiOn is True:
            for DBname, symbol in self.info_symbols:
                info_collection[DBname + " " + symbol] = self.dbClient[DBname][symbol]

        self.output("Start loading historical data")

        # Choose data type based on backtest mode
        if self.mode == self.BAR_MODE:
            self.dataClass = CtaBarData
            self.func      = self.newBar
        else:
            self.dataClass = CtaTickData
            self.func = self.newTick

        # Load initializing data
        self.loadInitData(collection, inf=info_collection)

        # Load backtest data (exclude initializing data)
        if not self.dataEndDate:
            # If "End Date" is not set, retreat data up to today
            flt = {'datetime': {'$gte': self.strategyStartDate}}
        else:
            flt = {'datetime': {'$gte': self.strategyStartDate,
                                '$lte': self.dataEndDate}}
        self.dbCursor = collection.find(flt)

        if self.MultiOn is True:
            for db in info_collection:
                self.InfoCursor[db] = info_collection[db].find(flt)
            self.output(
                "Data loading completed, data volumn: %s" % (self.initCursor.count() + self.dbCursor.count() + \
                                                             sum([i.count() for i in self.InfoCursor.values()])))
        else:
            self.output("Data loading completed, data volumn: %s" % (self.initCursor.count() + self.dbCursor.count()))

    # ----------------------------------------------------------------------
    def runBacktesting(self):

        """Run backtesting"""

        # Load historical data
        self.loadHistoryData()

        self.output("Start backtesing!")

        self.strategy.inited = True
        self.strategy.onInit()
        self.output("Strategy initialsing complete")

        self.strategy.trading = True
        self.strategy.onStart()
        self.output("Strategy started")

        self.output("Processing historical data...")

        dataClass = self.dataClass
        func = self.func
        for d in self.dbCursor:
            data = dataClass()
            data.__dict__ = d
            func(data)

        self.output("No more historical data")

    # ----------------------------------------------------------------------
    def checkInformationBar(self):
        """Update information symbols' data"""

        # If infobar is empty, which means it is the first time calling this method
        if self.infobar == {}:
            for info_symbol in self.InfoCursor:
                try:
                    self.infobar[info_symbol] = next(self.InfoCursor[info_symbol])
                except StopIteration:
                    print "Data of information symbols is empty! Input must be a list, not str."
                    raise

        temp = {}
        for info_symbol in self.infobar:

            data = self.infobar[info_symbol]

            # Update data only when Time Stamp is matched
            if (data is not None) and (data['datetime'] <= self.dt):

                try:
                    temp[info_symbol] = CtaBarData()
                    temp[info_symbol].__dict__ = data
                    self.infobar[info_symbol] = next(self.InfoCursor[info_symbol])
                except StopIteration:
                    self.infobar[info_symbol] = None
                    self.output("No more data in information database.")
            else:
                temp[info_symbol] = None

        return temp

    # ----------------------------------------------------------------------
    def newBar(self, bar):

        """new ohlc Bar"""
        self.bar = bar
        self.dt = bar.datetime
        self.crossLimitOrder()  # 先撮合限价单
        self.crossStopOrder()  # 再撮合停止单
        if self.MultiOn is True:
            self.strategy.onBar(bar, infobar=self.checkInformationBar())  # 推送K线到策略中
        else:
            self.strategy.onBar(bar)  # 推送K线到策略中


########################################################################

