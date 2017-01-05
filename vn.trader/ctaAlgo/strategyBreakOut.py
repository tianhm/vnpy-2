# encoding: UTF-8
"""
This file tweaks ctaTemplate Module to suit multi-TimeFrame strategies.
"""

from ctaBase import *
from ctaTemplate import CtaTemplate
import numpy as np

########################################################################
class BreakOut(CtaTemplate):

    """
    "BreakOut" class inherit from "CtaTemplate" class.

    "infoArray" is a dictionary, which is to store information symbols.

    Some ideas have to be known:
    1. An execution symbol contains the information of which instrument to trade (instrument),
    and how often to trade (time frame).
    For example, "@GC_15m" means trading "Gold" in 15 minutes bar.

    2. Information symbols cannot be traded, which are to provide additional information for trading.

    3. An information symbol can be the same as execution symbol with a different TimeFrame,
    or a different instrument.
    For example, "@GC_30m" or "@CL_1m" can be information symbol for "@GC_1m".


    To refer an price array of information symbol, use:
    self.infoArray["Name of Database + Space + Name of Collection"]["close"]
    self.infoArray["Name of Database + Space + Name of Collection"]["high"]
    self.infoArray["Name of Database + Space + Name of Collection"]["low"]


    To refer the latest price of information symbol, use:
    self.infoBar["Name of Database + Space + Name of Collection"]

    Return a "ctaBarData" instance or None (there is no new information data, while new trading data is occured.)
    """

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """
        Intraday breakout trading strategy. There are many ways of "Exit", in this file, only technical exit
        will be used.
        This strategy can only be backtested in "Bar Mode".
        """

        className = 'BreakOut'
        author = 'Joe'

        # Inherit from "ctaEngine" object
        super(BreakOut, self).__init__(ctaEngine, setting)

        # Set dictionaries for storing data of information symbols
        self.infoArray = {}
        self.initInfobar = {}
        self.infoBar = {}

        # Set parameters for buffer size
        self.bufferSize = 100
        self.bufferCount = 0
        self.initDays = 10

        # set parameters
        self.pOBO_Mult = 0.5           # Calculate breakout level
        # self.pProtMult = 2           # Multiplier of ATR stop loss
        # self.pProfitMult = 2         # Multiplier of take profit to stop loss
        # self.SlTp_On = False         # SL/TP ON/OFF
        # self.EODTime = 15            # The deadline of "End of Day" Exit

        self.vOBO_stretch = EMPTY_FLOAT
        self.vOBO_initialpoint = EMPTY_FLOAT
        self.vOBO_level_L = EMPTY_FLOAT
        self.vOBO_level_S = EMPTY_FLOAT

        self.orderList = []

        # List of Parameters
        paramList = ['name',
                     'className',
                     'author',
                     'pOBO_Mult',
                     'pProtMult',
                     'pProfitMult',
                     'SlTp_On',
                     'EODTime']

        # List of Variances
        varList = ['vOBO_stretch',
                   'vOBO_initialpoint',
                   'vOBO_level_L',
                   'vOBO_level_S']

        # ----------------------------------------------------------------------
    def onInit(self):
        """Strategy initialization (user have to define this method)"""

        self.writeCtaLog('%s Strategy Initializing' % self.name)

        # Load historical data, initialize strategy parameters by data playback.
        initData = self.loadBar(self.initDays)
        for bar in initData:

            # Update new bar, check whether the Time Stamp matching any information bar
            ibar = self.checkInfoBar(bar)
            self.onBar(bar, infobar=ibar)

        self.putEvent()

    #----------------------------------------------------------------------
    def onStart(self):
        """Strategy starting (user have to define this method)"""

        self.writeCtaLog("%s Strategy Starting" %self.name)
        self.putEvent()

    #----------------------------------------------------------------------
    def onStop(self):
        """Strategy stopping (user have to define this method)"""

        self.writeCtaLog('%s Strategy Stopping' %self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def checkInfoBar(self, bar):
        """Update information symbol in initialization process (won't be called after initalization)"""

        initInfoCursorDict = self.ctaEngine.initInfoCursor

        # Information data is temporarily stored in "initInfobar" dictionary and waiting for being pushed.
        # Only one price for each information symbols are stored in "initInfoba".
        # If dictionary "initInfobar" is empty, insert first data record
        if self.initInfobar == {}:
            for info_symbol in initInfoCursorDict:
                try:
                    self.initInfobar[info_symbol] = next(initInfoCursorDict[info_symbol])
                except StopIteration:
                    print "Data of information symbols is empty! Input is a list, not str."
                    raise

        # If any symbol's Time Stamp is matched with execution symbol's TimeStamp, return the data that
        # stored in "initInfobar", then update "initInfobar".
        temp = {}
        for info_symbol in self.initInfobar:

            data = self.initInfobar[info_symbol]

            # Replace old data by new data, when Time Stamp is matched

            if (data is not None) and (data['datetime'] <= bar.datetime):

                try:
                    temp[info_symbol] = CtaBarData()
                    temp[info_symbol].__dict__ = data
                    self.initInfobar[info_symbol] = next(initInfoCursorDict[info_symbol])
                except StopIteration:
                    self.initInfobar[info_symbol] = None
                    self.ctaEngine.output("No more data for initializing %s." % (info_symbol,))
            else:
                temp[info_symbol] = None

        return temp

    # ----------------------------------------------------------------------
    def updateInfoArray(self, infobar):
        """
        Recieve information data, update price array dictionary for information symbols.
        Input is a dictionary of "bar", output is a dictionary of "array".
        """

        for name in infobar:

            data = infobar[name]

            # First time initialization, construct empty arrays
            if len(self.infoArray) < len(infobar):
                self.infoArray[name] = {
                    "close": np.zeros(self.bufferSize),
                    "high": np.zeros(self.bufferSize),
                    "low": np.zeros(self.bufferSize),
                    "open": np.zeros(self.bufferSize)
                }

            # If there is not new data, do nothing. Else, append new data to the end of array, and
            # remove the first data of the array (roll over).
            if data is None:
                pass

            else:
                self.infoArray[name]["close"][0:self.bufferSize - 1] = \
                    self.infoArray[name]["close"][1:self.bufferSize]
                self.infoArray[name]["high"][0:self.bufferSize - 1] = \
                    self.infoArray[name]["high"][1:self.bufferSize]
                self.infoArray[name]["low"][0:self.bufferSize - 1] = \
                    self.infoArray[name]["low"][1:self.bufferSize]
                self.infoArray[name]["open"][0:self.bufferSize - 1] = \
                    self.infoArray[name]["open"][1:self.bufferSize]

                self.infoArray[name]["close"][-1] = data.close
                self.infoArray[name]["high"][-1] = data.high
                self.infoArray[name]["low"][-1] = data.low
                self.infoArray[name]["open"][-1] = data.open

    # ----------------------------------------------------------------------
    def onBar(self, bar, **kwargs):
        """Recieve Bar data (user have to define this method)"""

        # Update infomation data
        # "infobar" is a dictionary
        # "infobar"是由不同时间或不同品种的品种数据组成的字典, 如果和执行品种的 TimeStamp 不匹配,
        # 则传入的是"None", 当time stamp和执行品种匹配时, 传入的是"Bar"
        if "infobar" in kwargs:
            self.infoBar = kwargs["infobar"]
            self.updateInfoArray(kwargs["infobar"])

        # 若读取的缓存数据不足, 不考虑交易
        self.bufferCount += 1
        if self.bufferCount < self.bufferSize:
            return

        # 计算指标数值
        a = np.sum(self.infoArray["TestData @GC_1D"]["close"])
        if a == 0.0:
            return

        # Only updating indicators when information bar changes
        # 只有在30min或者1d K线更新后才更新指标
        TradeOn = False
        if any([i is not None for i in self.infoBar]):
            TradeOn = True
            self.vRange = self.infoArray["TestData @GC_1D"]["high"][-1] -\
                          self.infoArray["TestData @GC_1D"]["low"][-1]
            self.vOBO_stretch = self.vRange * self.pOBO_Mult
            self.vOBO_initialpoint = self.infoArray["TestData @GC_1D"]["close"][-1]
            self.vOBO_level_L = self.vOBO_initialpoint + self.vOBO_stretch
            self.vOBO_level_S = self.vOBO_initialpoint - self.vOBO_stretch

            self.atrValue30M = talib.abstract.ATR(self.infoArray["TestData @GC_30M"])[-1]

        # 判断是否要进行交易

        # 当前无仓位
        if (self.pos == 0 and TradeOn == True):

            # 撤销之前发出的尚未成交的委托（包括限价单和停止单）
            for orderID in self.orderList:
                self.cancelOrder(orderID)
            self.orderList = []

            # 若上一个30分钟K线的最高价大于OBO_level_L
            # 且当前的价格大于OBO_level_L, 则买入
            if self.infoArray["TestData @GC_30M"]["high"][-1] > self.vOBO_level_L:

                if bar.close > self.vOBO_level_L:

                    self.buy(bar.close + 0.5, 1)

                    # 下单后, 在下一个30Min K线之前不交易
                    TradeOn = False

            # 若上一个30分钟K线的最高价低于OBO_level_S
            # 且当前的价格小于OBO_level_S, 则卖出
            elif self.infoArray["TestData @GC_30M"]["low"][-1] < self.vOBO_level_S:

                if bar.close < self.vOBO_level_S:

                    self.short(bar.close - 0.5, 1)

                    # 下单后, 在下一个30Min K线之前不交易
                    TradeOn = False

        # 持有多头仓位
        elif self.pos > 0:

            # 当价格低于initialpoint水平, 出场
            if bar.close < self.vOBO_initialpoint:
                self.sell(bar.close - 0.5 , 1)

        # 持有空头仓位
        elif self.pos < 0:

            # 当价格高于initialpoint水平, 出场
            if bar.close > self.vOBO_initialpoint:
                self.cover(bar.close + 0.5, 1)


        # 发出状态更新事件
        self.putEvent()

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """Generate order information (user have to define this method)"""
        pass

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """Generate trade information (user have to define this method)"""
        # In backtest engine, no trade is executed. This method still needs to be defined, but
        # remains empty.
        pass


if __name__ == '__main__':
    # 提供直接双击回测的功能
    # 导入PyQt4的包是为了保证matplotlib使用PyQt4而不是PySide，防止初始化出错
    from ctaBacktestMultiTF import *
    from PyQt4 import QtCore, QtGui
    import time

    '''
    创建回测引擎
    设置引擎的回测模式为K线
    设置回测用的数据起始日期
    载入历史数据到引擎中
    在引擎中创建策略对象

    Create backtesting engine
    Set backtest mode as "Bar"
    Set "Start Date" of data range
    Load historical data to engine
    Create strategy instance in engine
    '''
    engine = BacktestEngineMultiTF()
    engine.setBacktestingMode(engine.BAR_MODE)
    engine.setStartDate('20120101')
    engine.setEndDate('20150101')
    engine.setDatabase("TestData", "@GC_1M", info_symbol=[("TestData","@GC_30M"),
                                                          ("TestData","@GC_1D")])

    # Set parameters for strategy
    engine.initStrategy(BreakOut, {})

    # 设置产品相关参数
    engine.setSlippage(0.2)  # 股指1跳
    engine.setCommission(0.3 / 10000)  # 万0.3
    engine.setSize(1)  # 股指合约大小

    # 开始跑回测
    start = time.time()

    engine.runBacktesting()

    # 显示回测结果
    engine.showBacktestingResult()

    print 'Time consumed：%s' % (time.time() - start)