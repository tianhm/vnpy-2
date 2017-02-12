# encoding: UTF-8
"""
This file tweaks ctaTemplate Module to suit multi-TimeFrame strategies.

author: Joe Zhou
"""

from ctaBase import *
from ctaTemplate import CtaTemplate
import numpy as np
import talib

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
    self.infoArray["Name of Collection"]["close"]
    self.infoArray["Name of Collection"]["high"]
    self.infoArray["Name of Collection"]["low"]


    To refer the latest price of information symbol, use:
    self.infoBar["Name of Collection"]

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
        '''
        Update infomation data

        "infobar" is a dictionary.
        The keys of "inforbar" are all the information symbols.
        The items of "inforbar" is a "Bar" instance or "None".

        For example, execution symbol is "@GC_15m", information symbol is "@GC_60m".
        The information data is store in inforbar["@GC_60m"].

        When the execution Time Stamp is "9:45", since it doesn't belong to time frame 60 minutes.
        inforbar["@GC_60m"] is "None".

        When the execution Time Stamp is "10:00", since it belongs to time frame 60 minutes.
        inforbar["@GC_60m"] is a ctaBar instance.

        '''

        if "infobar" in kwargs:
            self.infoBar = kwargs["infobar"]
            self.updateInfoArray(kwargs["infobar"])

        # Do not trade until buffer zone has enough data
        self.bufferCount += 1
        if self.bufferCount < self.bufferSize:
            return

        a = np.sum(self.infoArray["@GC_1D"]["close"])
        if a == 0.0:
            return

        # When the flag is "False", do not trade (place order)
        TradeOn = False

        # Only updating indicators every 30 or 60 minute
        if any([i is not None for i in self.infoBar]):

            # Only place order when indicators are updated
            TradeOn = True

            ########################################################################
            # Calculate indicators
            ########################################################################

            self.vRange = self.infoArray["@GC_1D"]["high"][-1] -\
                          self.infoArray["@GC_1D"]["low"][-1]
            self.vOBO_stretch = self.vRange * self.pOBO_Mult
            self.vOBO_initialpoint = self.infoArray["@GC_1D"]["close"][-1]
            self.vOBO_level_L = self.vOBO_initialpoint + self.vOBO_stretch
            self.vOBO_level_S = self.vOBO_initialpoint - self.vOBO_stretch

            self.atrValue30M = talib.abstract.ATR(self.infoArray["@GC_30T"])[-1]


        ########################################################################
        # The rules of trading (open/close position)
        ########################################################################

        # If "TradeOn" flag is "False", skip the loop

        # If no position holds, and "TradeOn" flag is "True"
        if (self.pos == 0 and TradeOn == True):

            # Cancel the orders that placed earlier, but did not trigger (including limit order and stop order)
            for orderID in self.orderList:
                self.cancelOrder(orderID)
            self.orderList = []

            ########################################################################
            # If "high" of last 30M Bar is larger than OBO_level_L, and "close" of
            # current Bar is larger than OBO_level_L, then buy:
            ########################################################################
            if self.infoArray["@GC_30T"]["high"][-1] > self.vOBO_level_L:

                if bar.close > self.vOBO_level_L:

                    self.buy(bar.close + 0.5, 1)

            ########################################################################
            # If "low" of last 30M Bar is smaller than OBO_level_S, and "close" of
            # current Bar is lower than OBO_level_S, then sell:
            ########################################################################
            elif self.infoArray["@GC_30T"]["low"][-1] < self.vOBO_level_S:

                if bar.close < self.vOBO_level_S:

                    self.short(bar.close - 0.5, 1)

        ########################################################################
        # If current position is "Long"
        ########################################################################
        elif self.pos > 0:

            # Sell when current close price is lower than initial point
            if bar.close < self.vOBO_initialpoint:
                self.sell(bar.close - 0.5 , 1)

        ########################################################################
        # If current position is "Short"
        ########################################################################
        elif self.pos < 0:

            # Buy when current close price is higher than initial point
            if bar.close > self.vOBO_initialpoint:
                self.cover(bar.close + 0.5, 1)

        # Update event status
        self.putEvent()

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """Generate order information (user have to define this method)"""
        pass

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """Generate trade information (user have to define this method)"""
        # In backtest engine, no trade is executed, but in order to keeping the consistence between
        # "ctaBacktestEngine" and "ctaEngine", this method still needs to be defined. Just remain empty.
        pass


if __name__ == '__main__':

    from ctaBacktestMultiTF import *
    import time

    '''
    Create backtesting engine
    Set backtest mode as "Bar"
    Set "Start Date" and "End Date"
    Load historical data to engine
    Create strategy instance in engine
    '''
    engine = BacktestEngineMultiTF()
    engine.setBacktestingMode(engine.BAR_MODE)
    engine.setStartDate('20100101')
    engine.setEndDate('20160101')
    # engine.setDatabase("SQLite", "ZCDatabase", "@GC_1T", info_symbol=[("ZCDatabase","@GC_30T"),
    #                                                                      ("ZCDatabase","@GC_1D")])

    engine.setDatabase("MongoDB", "TestData", "@GC_1T", info_symbol=[("TestData", "@GC_30T"),
                                                                     ("TestData", "@GC_1D")])

    # Set parameters for strategy
    engine.initStrategy(BreakOut, {})

    # Set parameters for instrument
    engine.setSlippage(0.2)
    engine.setRate(0.3 / 10000)
    engine.setSize(1)

    # Start backtesting
    start = time.time()

    engine.runBacktesting()

    # Show backtesting result
    engine.showBacktestingResult()

    print 'Time consumed：%s' % (time.time() - start)