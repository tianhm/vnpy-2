# encoding: UTF-8
"""
This file tweaks ctaTemplate Module to suit multi-TimeFrame strategies.
"""

from strategyAtrRsi import *
from ctaBase import *
from ctaTemplate import CtaTemplate

########################################################################
class TC11(CtaTemplate):

    # Strategy name and author
    className = "TC11"
    author = "Zenacon"

    # Set MongoDB DataBase
    barDbName = "TestData"

    # Strategy parameters
    pGeneric_prd = 21
    pGeneric_on = True

    pATRprd_F = 13
    pATRprd_M = 21
    pATRprd_S = 63

    pBOSSplus_prd = 98
    pBOSSminus_prd = 22

    if pGeneric_on == 0:
        pRSIprd = 20
        pBBprd = 10
        pBB_ATRprd = 15
        pATRprd = 21
        pDMIprd = 21
    else:
        pRSIprd =       \
        pBBprd =        \
        pBB_ATRprd =    \
        pATRprd =       \
        pDMIprd = pGeneric_prd

    pBOSS_Mult = 1.75

    # Strategy variables
    vOBO_initialpoint = EMPTY_FLOAT
    vOBO_Stretch = EMPTY_FLOAT
    vOBO_level_L = EMPTY_FLOAT
    vOBO_level_S = EMPTY_FLOAT

    # parameters' list, record names of parameters
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol']

    # variables' list, record names of variables
    varList = ['inited',
               'trading',
               'pos']

    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(TC11, self).__init__(ctaEngine, setting)

    # ----------------------------------------------------------------------
    def onBar(self, bar, **kwargs):
        """收到Bar推送（必须由用户继承实现）"""
        # 撤销之前发出的尚未成交的委托（包括限价单和停止单）
        for orderID in self.orderList:
            self.cancelOrder(orderID)
        self.orderList = []

        # Record new information bar
        if "infobar" in kwargs:
            for i in kwargs["infobar"]:
                if kwargs["infobar"][i] is None:
                    pass
                else:
                    # print kwargs["infobar"][i]["close"]
                    self.closeArray[0:self.bufferSize - 1] = self.closeArray[1:self.bufferSize]
                    self.highArray[0:self.bufferSize - 1] = self.highArray[1:self.bufferSize]
                    self.lowArray[0:self.bufferSize - 1] = self.lowArray[1:self.bufferSize]

                    self.closeArray[-1] = bar.close
                    self.highArray[-1] = bar.high
                    self.lowArray[-1] = bar.low

        """
        Record new bar
        """
        self.closeArray[0:self.bufferSize - 1] = self.closeArray[1:self.bufferSize]
        self.highArray[0:self.bufferSize - 1] = self.highArray[1:self.bufferSize]
        self.lowArray[0:self.bufferSize - 1] = self.lowArray[1:self.bufferSize]

        self.closeArray[-1] = bar.close
        self.highArray[-1] = bar.high
        self.lowArray[-1] = bar.low

        self.bufferCount += 1
        if self.bufferCount < self.bufferSize:
            return

        """
        Calculate Indicators
        """

        vOBO_initialpoint = self.dataHTF_filled['Open']
        vOBO_Stretch = self.vATR['htf'].m * self.pBOSS_Mult

        self.atrValue = talib.ATR(self.highArray,
                                  self.lowArray,
                                  self.closeArray,
                                  self.atrLength)[-1]
        self.atrArray[0:self.bufferSize - 1] = self.atrArray[1:self.bufferSize]
        self.atrArray[-1] = self.atrValue

        self.atrCount += 1
        if self.atrCount < self.bufferSize:
            return

        self.atrMa = talib.MA(self.atrArray,
                              self.atrMaLength)[-1]
        self.rsiValue = talib.RSI(self.closeArray,
                                  self.rsiLength)[-1]

        # 判断是否要进行交易

        # 当前无仓位
        if self.pos == 0:
            self.intraTradeHigh = bar.high
            self.intraTradeLow = bar.low

            # ATR数值上穿其移动平均线，说明行情短期内波动加大
            # 即处于趋势的概率较大，适合CTA开仓
            if self.atrValue > self.atrMa:
                # 使用RSI指标的趋势行情时，会在超买超卖区钝化特征，作为开仓信号
                if self.rsiValue > self.rsiBuy:
                    # 这里为了保证成交，选择超价5个整指数点下单
                    self.buy(bar.close + 5, 1)

                elif self.rsiValue < self.rsiSell:
                    self.short(bar.close - 5, 1)

        # 持有多头仓位
        elif self.pos > 0:
            # 计算多头持有期内的最高价，以及重置最低价
            self.intraTradeHigh = max(self.intraTradeHigh, bar.high)
            self.intraTradeLow = bar.low
            # 计算多头移动止损
            longStop = self.intraTradeHigh * (1 - self.trailingPercent / 100)
            # 发出本地止损委托，并且把委托号记录下来，用于后续撤单
            orderID = self.sell(longStop, 1, stop=True)
            self.orderList.append(orderID)

        # 持有空头仓位
        elif self.pos < 0:
            self.intraTradeLow = min(self.intraTradeLow, bar.low)
            self.intraTradeHigh = bar.high

            shortStop = self.intraTradeLow * (1 + self.trailingPercent / 100)
            orderID = self.cover(shortStop, 1, stop=True)
            self.orderList.append(orderID)

        # 发出状态更新事件
        self.putEvent()

########################################################################
class Prototype(AtrRsiStrategy):

    infoArray = {}

    def __int__(self):
        super(Prototype, self).__int__()

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' % self.name)

        # 初始化RSI入场阈值
        self.rsiBuy = 50 + self.rsiEntry
        self.rsiSell = 50 - self.rsiEntry

        # 载入历史数据，并采用回放计算的方式初始化策略数值
        initData = self.loadBar(self.initDays)
        for bar in initData:
            self.onBar(bar)

        self.putEvent()

    # ----------------------------------------------------------------------
    def onBar(self, bar, **kwargs):
        """收到Bar推送（必须由用户继承实现）"""
        # 撤销之前发出的尚未成交的委托（包括限价单和停止单）
        if "infobar" in kwargs:

            for name in kwargs["infobar"]:

                data = kwargs["infobar"][name]

                # Initialize infomation data
                if self.infoArray == {}:
                    self.infoArray[name] = {
                        "close" :np.zeros(self.bufferSize),
                        "high"  :np.zeros(self.bufferSize),
                        "low"   :np.zeros(self.bufferSize)
                    }

                if data is None:
                    pass

                else:
                    self.infoArray[name]["close"][0:self.bufferSize - 1] = \
                        self.infoArray[name]["close"][1:self.bufferSize]
                    self.infoArray[name]["high"][0:self.bufferSize - 1] = \
                        self.infoArray[name]["high"][1:self.bufferSize]
                    self.infoArray[name]["low"][0:self.bufferSize - 1] = \
                        self.infoArray[name]["low"][1:self.bufferSize]

                    self.infoArray[name]["close"][-1] = data.close
                    self.infoArray[name]["high"][-1] = data.high
                    self.infoArray[name]["low"][-1] = data.low

        for orderID in self.orderList:
            self.cancelOrder(orderID)
        self.orderList = []

        # 保存K线数据
        self.closeArray[0:self.bufferSize - 1] = self.closeArray[1:self.bufferSize]
        self.highArray[0:self.bufferSize - 1] = self.highArray[1:self.bufferSize]
        self.lowArray[0:self.bufferSize - 1] = self.lowArray[1:self.bufferSize]

        self.closeArray[-1] = bar.close
        self.highArray[-1] = bar.high
        self.lowArray[-1] = bar.low

        self.bufferCount += 1
        if self.bufferCount < self.bufferSize:
            return

        # 计算指标数值
        # self.STFatrValue = talib.abstract.ATR(
        #     self.infoArray["@GC_30M"]
        # )
        # print self.STFatrValue

        self.atrValue = talib.ATR(self.highArray,
                                  self.lowArray,
                                  self.closeArray,
                                  self.atrLength)[-1]
        self.atrArray[0:self.bufferSize - 1] = self.atrArray[1:self.bufferSize]
        self.atrArray[-1] = self.atrValue

        self.atrCount += 1
        if self.atrCount < self.bufferSize:
            return

        self.atrMa = talib.MA(self.atrArray,
                              self.atrMaLength)[-1]
        self.rsiValue = talib.RSI(self.closeArray,
                                  self.rsiLength)[-1]

        # 判断是否要进行交易

        # 当前无仓位
        if self.pos == 0:
            self.intraTradeHigh = bar.high
            self.intraTradeLow = bar.low

            # ATR数值上穿其移动平均线，说明行情短期内波动加大
            # 即处于趋势的概率较大，适合CTA开仓
            if self.atrValue > self.atrMa:
                # 使用RSI指标的趋势行情时，会在超买超卖区钝化特征，作为开仓信号
                if self.rsiValue > self.rsiBuy:
                    # 这里为了保证成交，选择超价5个整指数点下单
                    self.buy(bar.close + 5, 1)

                elif self.rsiValue < self.rsiSell:
                    self.short(bar.close - 5, 1)

        # 持有多头仓位
        elif self.pos > 0:
            # 计算多头持有期内的最高价，以及重置最低价
            self.intraTradeHigh = max(self.intraTradeHigh, bar.high)
            self.intraTradeLow = bar.low
            # 计算多头移动止损
            longStop = self.intraTradeHigh * (1 - self.trailingPercent / 100)
            # 发出本地止损委托，并且把委托号记录下来，用于后续撤单
            orderID = self.sell(longStop, 1, stop=True)
            self.orderList.append(orderID)

        # 持有空头仓位
        elif self.pos < 0:
            self.intraTradeLow = min(self.intraTradeLow, bar.low)
            self.intraTradeHigh = bar.high

            shortStop = self.intraTradeLow * (1 + self.trailingPercent / 100)
            orderID = self.cover(shortStop, 1, stop=True)
            self.orderList.append(orderID)

        # 发出状态更新事件
        self.putEvent()


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
    engine.setStartDate('20150101')
    engine.setDatabase("TestData", "@GC_1M", info_symbol=["@GC_30M"])
    # Set parameters for strategy
    d = {'atrLength': 11}
    engine.initStrategy(Prototype, d)

    # 设置产品相关参数
    engine.setSlippage(0.2)  # 股指1跳
    engine.setCommission(0.3 / 10000)  # 万0.3
    engine.setSize(300)  # 股指合约大小

    # 开始跑回测
    start = time.time()

    engine.runBacktesting()

    # 显示回测结果
    engine.showBacktestingResult()

    # 跑优化
    # setting = OptimizationSetting()                 # 新建一个优化任务设置对象
    # setting.setOptimizeTarget('capital')            # 设置优化排序的目标是策略净盈利
    # setting.addParameter('atrLength', 11, 20, 1)    # 增加第一个优化参数atrLength，起始11，结束12，步进1
    # setting.addParameter('atrMa', 20, 30, 5)        # 增加第二个优化参数atrMa，起始20，结束30，步进1

    # 性能测试环境：I7-3770，主频3.4G, 8核心，内存16G，Windows 7 专业版
    # 测试时还跑着一堆其他的程序，性能仅供参考


    # 运行单进程优化函数，自动输出结果，耗时：359秒
    # engine.runOptimization(AtrRsiStrategy, setting)

    # 多进程优化，耗时：89秒
    # engine.runParallelOptimization(AtrRsiStrategy, setting)

    print 'Time consumed：%s' % (time.time() - start)