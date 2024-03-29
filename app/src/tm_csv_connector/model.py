'''
models - database models for application
===========================================
'''

# standard

# pypi
from flask_sqlalchemy import SQLAlchemy

# home grown
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import mapped_column
from sqlalchemy import text
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

class ScannedBib(Base):
    __tablename__ = 'scannedbib'
    id           = Column(Integer(), primary_key=True)
    race_id      = mapped_column(ForeignKey('race.id'))
    race         = relationship('Race', back_populates='scannedbibs', foreign_keys=[race_id])
    order        = Column(Integer)
    bibno        = Column(Text)
    result       = relationship("Result", uselist=False, back_populates="scannedbib")
    
class Race(Base):
    __tablename__ = 'race'
    id          = Column(Integer(), primary_key=True)
    name        = Column(Text)
    date        = Column(Date)
    start_time  = Column(Double) # seconds since midnight
    results     = relationship('Result', back_populates='race', cascade='all, delete, delete-orphan')
    scannedbibs = relationship('ScannedBib', back_populates='race', foreign_keys=[ScannedBib.race_id], cascade='all, delete, delete-orphan')
    # next_scannedbib is set when there are more scanned bibs than there are results
    next_scannedbib_id = mapped_column(ForeignKey('scannedbib.id'))
    next_scannedbib    = relationship('ScannedBib', foreign_keys=[next_scannedbib_id])
    
    @hybrid_property
    def raceyear(self):
        return self.name + ' ' + self.date.strftime('%Y')
    
class Result(Base):
    __tablename__ = 'result'
    id           = Column(Integer(), primary_key=True)
    race_id      = mapped_column(ForeignKey('race.id'))
    race         = relationship('Race', back_populates='results')
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

class Setting(Base):
    __tablename__ = 'setting'
    id      = Column(Integer(), primary_key=True)
    name    = Column(Text)
    value   = Column(Text)
    