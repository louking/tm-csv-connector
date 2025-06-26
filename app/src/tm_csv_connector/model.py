'''
models - database models for application
===========================================
'''

# standard

# pypi
from flask_sqlalchemy import SQLAlchemy
from flask_security.models import fsqla_v3 as fsqla


# home grown
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import mapped_column
from sqlalchemy import text, func
from sqlalchemy.schema import FetchedValue

# set up database - SQLAlchemy() must be done after app.config SQLALCHEMY_* assignments
db = SQLAlchemy()
Table = db.Table
Index = db.Index
Column = db.Column
Integer = db.Integer
Float = db.Float
Double = db.Double
Boolean = db.Boolean
Decimal = db.DECIMAL
String = db.String
Text = db.Text
Date = db.Date
Time = db.Time
DateTime = db.DateTime
Sequence = db.Sequence
Enum = db.Enum
Interval = db.Interval
UniqueConstraint = db.UniqueConstraint
ForeignKey = db.ForeignKey
relationship = db.relationship
backref = db.backref
object_mapper = db.object_mapper
Base = db.Model

# flask security models
fsqla.FsModels.set_db_info(db)
class Role(Base, fsqla.FsRoleMixin):
    pass
class User(Base, fsqla.FsUserMixin):
    name = Column(Text)
    simruns = relationship('SimulationRun', back_populates='user', cascade='all, delete, delete-orphan')

class ScannedBib(Base):
    __tablename__ = 'scannedbib'
    id           = Column(Integer(), primary_key=True)
    # has race_id or simrun_id, but not both
    race_id      = mapped_column(ForeignKey('race.id'))
    race         = relationship('Race', back_populates='scannedbibs', foreign_keys=[race_id])
    simulationrun_id = mapped_column(ForeignKey('simulationrun.id'))
    simulationrun    = relationship('SimulationRun', back_populates='scannedbibs', foreign_keys=[simulationrun_id])

    order        = Column(Integer)
    bibno        = Column(Text)
    result       = relationship("Result", uselist=False, back_populates="scannedbib")
    
class ChipRead(Base):
    __tablename__ = 'chipread'
    id          = Column(Integer(), primary_key=True)
    race_id      = mapped_column(ForeignKey('race.id'))
    race         = relationship('Race', back_populates='chipreads')
    reader_id   = Column(String(1))
    receiver_id = Column(String(1))
    tag_id      = Column(String(12))
    bib         = Column(Integer)
    contig_ctr  = Column(Integer)
    date        = Column(Date)
    time        = Column(Decimal(7,2)) # max 86400.00 = 24*60*60 seconds
    rssi        = Column(Integer)
    types       = Column(Text)
    source      = Column(Text)  # file, live
    
    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

    # lookups by date/tag and date/tag/time need to be fast
    __tableargs__ = (
        Index('rdr_date_tag_idx', reader_id, date, tag_id),
        Index('rdr_date_bib_idx', reader_id, date, bib),
        Index('rdr_date_tag_time_idx', reader_id, date, tag_id, time),
    )

    @hybrid_property
    def display_date(self):
        return func.date_format(self.date, '%Y-%m-%d')
    
class ChipBib(Base):
    __tablename__ = 'chipbib'
    id          = Column(Integer(), primary_key=True)
    race_id      = mapped_column(ForeignKey('race.id'))
    race         = relationship('Race', back_populates='chipbibs')
    tag_id      = Column(String(12))
    bib         = Column(Integer)
    
    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

    # lookups by race, tag need to be fast
    __tableargs__ = (
        Index('race_tag_idx', race_id, tag_id),
    )


class Race(Base):
    __tablename__ = 'race'
    id          = Column(Integer(), primary_key=True)
    name        = Column(Text)
    date        = Column(Date)
    start_time  = Column(Double) # seconds since midnight
    results     = relationship('Result', back_populates='race', cascade='all, delete, delete-orphan')
    scannedbibs = relationship('ScannedBib', back_populates='race', foreign_keys=[ScannedBib.race_id], cascade='all, delete, delete-orphan')
    chipreads   = relationship('ChipRead', back_populates='race', foreign_keys=[ChipRead.race_id], cascade='all, delete, delete-orphan')
    chipbibs    = relationship('ChipBib', back_populates='race', foreign_keys=[ChipBib.race_id], cascade='all, delete, delete-orphan')
    
    # next_scannedbib is set when there are more scanned bibs than there are results
    # OBSOLETE
    next_scannedbib_id = mapped_column(ForeignKey('scannedbib.id'))
    next_scannedbib    = relationship('ScannedBib', foreign_keys=[next_scannedbib_id])
    
    @hybrid_property
    def raceyear(self):
        return self.name + ' ' + self.date.strftime('%Y') if self.date else ''
    
    @raceyear.inplace.expression
    @classmethod
    def _raceyear_expression(cls):
        return cls.name + ' ' + func.year(cls.date) if cls.date else ''
    
class Result(Base):
    __tablename__ = 'result'
    id           = Column(Integer(), primary_key=True)
    # has race_id or simrun_id, but not both
    race_id      = mapped_column(ForeignKey('race.id'))
    race         = relationship('Race', back_populates='results')
    simulationrun_id = mapped_column(ForeignKey('simulationrun.id'))
    simulationrun    = relationship('SimulationRun', back_populates='results')
    tmpos        = Column(Integer)
    place        = Column(Integer)
    scannedbib_id = mapped_column(ForeignKey('scannedbib.id'))
    scannedbib    = relationship('ScannedBib', back_populates='result')
    had_scannedbib = Column(Boolean, default=False)
    bibno        = Column(Text)
    time         = Column(Float)
    is_confirmed = Column(Boolean, default=False)
    
    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

class BluetoothType(Base):
    __tablename__ = 'bluetoothtype'
    id          = Column(Integer(), primary_key=True)
    type        = Column(Text)
    description = Column(Text)
    devices     = relationship('BluetoothDevice', back_populates='type', cascade='all, delete, delete-orphan')
    
    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

class BluetoothDevice(Base):
    __tablename__ = 'bluetoothdevice'
    id          = Column(Integer(), primary_key=True)
    name        = Column(Text)
    type_id     = mapped_column(ForeignKey('bluetoothtype.id'))
    type        = relationship('BluetoothType', back_populates='devices')
    hwaddr      = Column(Text)
    
    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

class ChipReader(Base):
    __tablename__ = 'chipreader'
    id          = Column(Integer(), primary_key=True)
    name        = Column(Text)
    reader_id   = Column(String(1))
    ipaddr      = Column(Text)
    fport       = Column(Integer) # port to retrieve filtered reads
    
    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

class AppLog(Base):
    __tablename__ = 'applog'
    id          = Column(Integer(), primary_key=True)
    time        = Column(DateTime)
    info        = Column(Text)
    
    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

    
class Setting(Base):
    __tablename__ = 'setting'
    id      = Column(Integer(), primary_key=True)
    name    = Column(Text)
    value   = Column(Text)

class Simulation(Base):
    __tablename__ = 'simulation'
    id      = Column(Integer(), primary_key=True)
    name    = Column(Text)
    events  = relationship('SimulationEvent', back_populates='simulation', cascade='all, delete, delete-orphan')
    vectors = relationship('SimulationVector', back_populates='simulation', cascade='all, delete, delete-orphan')
    runs = relationship('SimulationRun', back_populates='simulation', cascade='all, delete, delete-orphan')
    
    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

# simulation actions
etype_type = ['timemachine', 'scan']
# user initiated scan actions
etype_type += ['insert', 'delete', 'use']
# user initiated file actions
etype_type += ['confirm', 'refresh']

class SimulationEvent(Base):
    __tablename__ = 'simulationevent'
    id      = Column(Integer(), primary_key=True)
    simulation_id = mapped_column(ForeignKey('simulation.id'))
    simulation = relationship('Simulation', back_populates='events')
    time    = Column(Float)
    etype   = Column(Text, nullable=False)
    bibno   = Column(Text)

    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

class SimulationVector(Base):
    __tablename__ = 'simulationvector'
    id      = Column(Integer(), primary_key=True)
    simulation_id = mapped_column(ForeignKey('simulation.id'))
    simulation = relationship('Simulation', back_populates='vectors')
    order   = Column(Integer)
    time    = Column(Float)
    bibno   = Column(Text)

    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

class SimulationRun(Base):
    __tablename__ = 'simulationrun'
    id      = Column(Integer(), primary_key=True)
    simulation_id = mapped_column(ForeignKey('simulation.id'))
    simulation = relationship('Simulation', back_populates='runs')
    user_id = mapped_column(ForeignKey('user.id'))
    user = relationship('User', back_populates='simruns')
    timestarted = Column(DateTime)
    timeended = Column(DateTime)
    score = Column(Float)

    simresults  = relationship('SimulationResult', back_populates='simulationrun', cascade='all, delete, delete-orphan')
    results     = relationship('Result', back_populates='simulationrun', cascade='all, delete, delete-orphan')
    scannedbibs = relationship('ScannedBib', back_populates='simulationrun', foreign_keys=[ScannedBib.simulationrun_id], cascade='all, delete, delete-orphan')

    # next_scannedbib is set when there are more scanned bibs than there are results
    # OBSOLETE
    next_scannedbib_id = mapped_column(ForeignKey('scannedbib.id'))
    next_scannedbib    = relationship('ScannedBib', foreign_keys=[next_scannedbib_id])

    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

    @hybrid_property
    def userstart(self):
        return self.user.name + ' ' + self.timestarted.strftime('%Y-%m-%d %H:%M')
    
    @userstart.inplace.expression
    @classmethod
    def _userstart_expression(cls):
        return cls.user.name + ' ' + cls.date

    @hybrid_property
    def usersimstart(self):
        return self.user.name + ' ' + self.simulation.name + ' '  + self.timestarted.strftime('%Y-%m-%d %H:%M')
    
    @usersimstart.inplace.expression
    @classmethod
    def _usersimstart_expression(cls):
        return cls.user.name + ' ' + cls.simulation.name + ' '  + cls.date

class SimulationResult(Base):
    __tablename__ = 'simulationresult'
    id      = Column(Integer(), primary_key=True)
    simulationrun_id = mapped_column(ForeignKey('simulationrun.id'))
    simulationrun = relationship('SimulationRun', back_populates='simresults')
    order   = Column(Integer)
    bibno   = Column(Text)
    time    = Column(Float)

    # track last update - https://docs.sqlalchemy.org/en/20/dialects/mysql.html#mysql-timestamp-onupdate
    update_time = Column(DateTime,
                         server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                         server_onupdate=FetchedValue()
                         )

