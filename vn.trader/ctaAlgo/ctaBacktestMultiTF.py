# encoding: UTF-8

'''
This file add multi Time Frame functionalities to CTA backtesting engine, the APIs are the
same as CTA engine. Real trading code can be directly used for backtesting.
'''

from __future__ import division
from vtFunction import loadMongoSetting
import pymongo

from ctaBacktesting import *

class BacktestEngineMultiTF(BacktestingEngine):

    def __init__(self):
        """Constructor"""
        super(BacktestEngineMultiTF, self).__init__()

        # List, input 2-value tuples, the first value is name of database, the second
        # value is name of collection. For example, ("TestData","@GC_30M")
        self.info_symbols   = []
        self.InfoCursor     = {}        # Dict, place information symbol data for backtesting
        self.initInfoCursor = {}        # Dict, place information symbol data for initializing
        self.infobar        = {}        # Dict, place the latest bar data for information symbols
        self.MultiOn        = False     # Boolean, check whether multi time frame is activated

    # ----------------------------------------------------------------------
    def setDatabase(self, dbType, dbName, symbol, **kwargs):
        """set database that provide historical data"""

        self.dbType = dbType
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
        """Load initialization data"""

        # $gte means "greater and equal to"
        # $lt means "less than"
        # Initializing data of execution symbol
        flt = {'datetime': {'$gte': self.dataStartDate,
                            '$lt': self.strategyStartDate}}
        self.initCursor = collection.find(flt)

        # Initializing data of information symbols
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

        # Choose data type based on backtest mode
        if self.mode == self.BAR_MODE:
            self.dataClass = CtaBarData
            self.func = self.newBar
        else:
            self.dataClass = CtaTickData
            self.func = self.newTick

        ###############################################################
        # Select type of database
        ###############################################################

        if self.dbType == "MongoDB":

            # Load data of execution symbol
            host, port = loadMongoSetting()

            self.dbClient = pymongo.MongoClient(host, port)
            collection = self.dbClient[self.dbName][self.symbol]

            # Load historical data of information symbols, construct a dictionary of Database
            # The values of dictionary are MongoDB.Client.
            info_collection = {}
            if self.MultiOn is True:
                for DBname, symbol in self.info_symbols:
                    info_collection[symbol] = self.dbClient[DBname][symbol]

            self.output("Start loading historical data from MongoDB")

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

        elif self.dbType == "SQLite":

            import sqlite3 as sq
            self.output("Start loading historical data from SQLite")

            # Define a function to read SQL data as dictionaries
            def dict_factory(cursor, row):
                d = {}
                for idx, col in enumerate(cursor.description):
                    new_name = col[0].lower()
                    if new_name == "datetime":
                        new_date = datetime.strptime(row[idx], '%Y-%m-%d %H:%M:%S')
                        d[new_name] = new_date
                    else:
                        d[new_name] = row[idx]

                return d

            ###############################################################
            # Load initialization data
            ###############################################################
            DBpath = "Z:\9Data\\1SQL_Database\%s" % (self.dbName)
            conn = sq.connect(DBpath)
            conn.row_factory = dict_factory
            exedb = conn.cursor()

            # Load data of execution symbol, then convert List of data to Generator
            self.initCursor = exedb.execute("""
            SELECT * FROM '%s' WHERE (DateTime >= '%s' and DateTime < '%s')
            """ % (self.symbol, self.dataStartDate, self.strategyStartDate))

            # Read data from cursor, generate a list of CtaData
            self.initData = []
            for d in self.initCursor:
                data = self.dataClass()
                data.__dict__ = d
                self.initData.append(data)

            ###############################################################
            # Load initialization data of information symbols, construct a dictionary of Database
            ###############################################################
            if self.MultiOn is True:
                for DBname, symbol in self.info_symbols:
                    temp = sq.connect(DBpath)
                    temp.row_factory = dict_factory
                    self.initInfoCursor[symbol] = temp.cursor()
                    self.initInfoCursor[symbol].execute("""
                    SELECT * FROM '%s' WHERE (DateTime >= '%s' and DateTime < '%s')
                    """ % (symbol, self.dataStartDate, self.strategyStartDate))

            ###############################################################
            # Load data for backtesting (exclude data for initializing)
            ###############################################################

            if not self.dataEndDate:
                # If "End Date" is not set, retreat data up to today
                self.dbCursor = exedb.execute("""
                                SELECT * FROM '%s' WHERE DateTime >= '%s'
                                """ % (self.symbol, self.strategyStartDate,))


                if self.MultiOn is True:
                    for DBname, symbol in self.info_symbols:
                        temp = sq.connect(DBpath)
                        temp.row_factory = dict_factory
                        self.InfoCursor[symbol] = temp.cursor()
                        self.InfoCursor[symbol].execute("""
                        SELECT * FROM '%s' WHERE DateTime >= '%s'
                        """ % (symbol, self.strategyStartDate))

            else:

                self.dbCursor = exedb.execute("""
                                SELECT * FROM '%s' WHERE (DateTime >= '%s' and DateTime < '%s')
                                """ % (self.symbol, self.strategyStartDate, self.dataEndDate))

                if self.MultiOn is True:
                    for DBname, symbol in self.info_symbols:
                        temp = sq.connect(DBpath)
                        temp.row_factory = dict_factory
                        self.InfoCursor[symbol] = temp.cursor()
                        self.InfoCursor[symbol].execute("""
                        SELECT * FROM '%s' WHERE (DateTime >= '%s' and DateTime < '%s')
                        """ % (symbol, self.strategyStartDate, self.dataEndDate))

            self.output(
                    "Data loading completed, execution data volumn: %s" % (len(self.initData)))



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
        self.crossLimitOrder()  # Check any limit order is triggered
        self.crossStopOrder()   # Check any stop order is triggered
        if self.MultiOn is True:
            self.strategy.onBar(bar, infobar=self.checkInformationBar())  # Push data (Bar) to strategy
        else:
            self.strategy.onBar(bar)  # Push data (Bar) to strategy


########################################################################

