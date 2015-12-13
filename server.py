from flask import Flask, render_template 
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, func, ForeignKey
from sqlalchemy.ext.declarative import declarative_base  
from sqlalchemy.orm import sessionmaker 
from datetime import timedelta, datetime
import flask 
import mysql.connector
import urllib.request
from io import BytesIO 
import re 
import configparser
from flask.ext.compress import Compress

import newrelic.agent
newrelic.agent.initialize('/etc/newrelic.ini')

compress = Compress()
 
app = Flask(__name__) 
app.debug = True
Compress(app)

config = configparser.ConfigParser()
config.read("config.cfg")


engine = create_engine(config["database"]["dbstring"], pool_recycle=3600)  
Base = declarative_base()  
  
class Downloads(Base):  
     __tablename__ = 'downloads'  
     url = Column(String(255), primary_key=True)  
  
class P5(Base):  
     __tablename__ = 'p5'  
     datetime = Column(DateTime, primary_key=True)  
     regionid = Column(String(100), primary_key=True)  
     rrp = Column(Float)  
     demand = Column(Float)  
     generation = Column(Float)  
     def as_dict(self):
          return {c.name: getattr(self, c.name) for c in self.__table__.columns}
  
class dispatchIS(Base):  
     __tablename__ = 'dispatchIS'  
     datetime = Column(DateTime, primary_key=True)  
     regionid = Column(String(100), primary_key=True)  
     rrp = Column(Float)  
     demand = Column(Float)  
     generation = Column(Float)  
     def as_dict(self):
          return {c.name: getattr(self, c.name) for c in self.__table__.columns}
class notices(Base):  
     __tablename__ = 'notices'  
     id = Column(Integer, primary_key=True)  
     datetime = Column(DateTime)  
     message = Column(String(500))  
     url = Column(String(255))  
class interconnect(Base):
     __tablename__ = 'interconnect-dispatchIS'
     datetime = Column(DateTime, primary_key=True)
     interconnectorid = Column(String(100), primary_key=True)
     meteredmwflow = Column(Float)
     mwflow = Column(Float)
     mwlosses = Column(Float)
     exportlimit = Column(Float)
     importlimit = Column(Float)  
     def as_dict(self):
          return {c.name: getattr(self, c.name) for c in self.__table__.columns}
  
class stationdata(Base):
     __tablename__ = 'stationdata'
     DUID = Column(String(255), primary_key=True)
     regcap = Column(Float)
     FuelSource = Column(String(255))
     FuelSourceDescriptior = Column(String(255))
     Tech = Column(String(255))
     TechDescription = Column(String(255))
     Participant = Column(String(255))
     StationName = Column(String(255))
     def as_dict(self):
          return {c.name: getattr(self, c.name) for c in self.__table__.columns}
class DispatchSCADA(Base):
     __tablename__ = 'DispatchSCADA'
     DUID = Column(String(255), primary_key=True)
     SETTLEMENTDATE = Column(DateTime, primary_key=True)
     SCADAVALUE = Column(Float)
     def as_dict(self):
          return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class CO2Factor(Base):
     __tablename__ = 'CO2Factor'
     DUID = Column(String(255), ForeignKey("DispatchSCADA.DUID"), primary_key=True)
     ReportDate = Column(DateTime, primary_key=True)
     Factor = Column(Float)
     def as_dict(self):
          return {c.name: getattr(self, c.name) for c in self.__table__.columns}

  
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, autocommit=True)
session = Session()




def dictfetchall(cursor):
    # Returns all rows from a cursor as a list of dicts
    desc = cursor.description
    return [dict(zip([col[0] for col in desc], row)) 
            for row in cursor.fetchall()]

def prettyNotice(noticeText):
    noticeText = re.sub(r"\r?\n-+\r?\nEND OF REPORT\r?\n-+", r"", noticeText)
    noticeText = re.sub(r"-+\r?\n(.+)\r?\n-+\r?\n", r"\n<h1>\1</h1>", noticeText)
    noticeText = re.sub(r"\r?\n-+\r?\n", r"\n<hr>", noticeText)
    noticeText = re.sub(r"\n([^\n\r:]+):\r?\n", r"<h2>\1</h2>", noticeText)
    noticeText = re.sub(r"\r?\n(.{3,15}):(.+)", r"\n<tr><td><b>\1 :</b></td><td>\2</td></tr>", noticeText)
    noticeText = re.sub(r"((<tr>.+</tr>\r?\n)+)", r"<table>\1</table>", noticeText)
    noticeText = re.sub(r"\r?\n\r?\n", r"\n<br>", noticeText)
    noticeText = re.sub(r"\n(?!<)(.+)", r"\1<br>\n", noticeText)
    noticeText = "<html><head><style>body {font-family: Sans-Serif;}</style></head><body>" + noticeText
    noticeText = noticeText + "</body></html>"
    return noticeText


@app.route("/notice/<id>")
def notice(id):
    url = "http://www.nemweb.com.au/Reports/CURRENT/Market_Notice/" + id
    data = urllib.request.urlopen(url).read().decode('iso-8859-1','ignore')
    data = prettyNotice(data)
    
    return flask.Response(data, mimetype="text/html")

	
@app.route("/")
def index():
    return render_template('index.html')
@app.route("/stations")
def stations():
    return render_template('stations.html')

@app.route("/env")
def env():
    return render_template('env.html')


@app.route("/stations-data")
def stationsdata():
    export = {}
    s = session.query(stationdata).all()
    for item in s:
         item = item.as_dict()
         export[item['DUID']] = item  
    return flask.jsonify(results=export)

@app.route("/co2-factor")
def co2factor():
    export = {}
#    s = session.query(CO2Factor).all()
#    s = engine.execute("select * from CO2Factor where ReportDate = (select MAX(ReportDate) from CO2Factor);")
    s = session.query(CO2Factor).filter(CO2Factor.ReportDate == session.query(func.max(CO2Factor.ReportDate)))
    for item in s:
#         item = dict(item.items())
         item = item.as_dict()
         export[item['DUID']] = item  
    return flask.jsonify(results=export)

@app.route("/station-history/<duid>")
def stationhistory(duid):
    duid = duid.replace("-slash-","/")
    s = session.query(DispatchSCADA).filter(DispatchSCADA.SETTLEMENTDATE > datetime.now() - timedelta(hours=72)).filter(DispatchSCADA.DUID == duid)
    export = {}
    for item in s:
         item = item.as_dict()
         #item['SETTLEMENTDATE'] = str(item['SETTLEMENTDATE'])
         export[str(item['SETTLEMENTDATE'])]=item
    return flask.jsonify(results=export)

@app.route("/stations-now")
def stationsnow():
    s = session.query(DispatchSCADA).filter(DispatchSCADA.SETTLEMENTDATE > datetime.now() - timedelta(hours=3))
    export = {}
    for item in s:
         item = item.as_dict()
         #item['SETTLEMENTDATE'] = str(item['SETTLEMENTDATE'])
         if item['DUID'] not in export:
             export[item['DUID']] = []
         export[item['DUID']].append(item)
    return flask.jsonify(results=export)


@app.route("/scada")
def scada():
    export = {}
#    s = engine.execute("select * from DispatchSCADA where SETTLEMENTDATE = (select MAX(SETTLEMENTDATE) from DispatchSCADA);")
    s = session.query(DispatchSCADA, CO2Factor.Factor).join(CO2Factor).filter(DispatchSCADA.SETTLEMENTDATE == session.query(func.max(DispatchSCADA.SETTLEMENTDATE))  ).filter(CO2Factor.ReportDate == session.query(func.max(CO2Factor.ReportDate)))
#    s = session.query(DispatchSCADA, DispatchSCADA.SETTLEMENTDATE == func.max(DispatchSCADA.SETTLEMENTDATE)).all()
    for item in s:
	 #cos = engine.execute("select * from CO2Factor where ReportDate = (select MAX(ReportDate) from CO2Factor);").all()
#         item = dict(item.items())
         co2 = item[1]
         item = item[0].as_dict()
         try:
              item['CO2E'] = co2 * item['SCADAVALUE']
#             cos = session.query(CO2Factor, CO2Factor.ReportDate == func.max(CO2Factor.ReportDate)).filter(CO2Factor.DUID == item['DUID']).all()
#             item['CO2E'] = cos[0][0].Factor * item['SCADAVALUE']
         except:
             pass
         item['SETTLEMENTDATE'] = str(item['SETTLEMENTDATE'])
         export[item['DUID']]=item
    return flask.jsonify(results=export)
	
@app.route("/dispatch")
def dispatch():
    s = session.query(dispatchIS).filter(dispatchIS.datetime > datetime.now() - timedelta(hours=48))
    export = {}
    for item in s:
         item = item.as_dict()
         if str(item['datetime']) not in export:
              export[str(item['datetime'])] = {}
         export[str(item['datetime'])][item['regionid']] = item
               
    return flask.jsonify(results=export)
@app.route("/interconnect")
def interconnectjson():
    s = session.query(interconnect).filter(interconnect.datetime > datetime.now() - timedelta(hours=48))
    export = {}
    for item in s:
         item = item.as_dict()
         if str(item['datetime']) not in export:
              export[str(item['datetime'])] = {}
         export[str(item['datetime'])][item['interconnectorid']] = item
               
    return flask.jsonify(results=export)
@app.route("/predictions")
def predictions():
    s = session.query(P5).filter(P5.datetime > datetime.now() - timedelta(minutes=5))
    export = {}
    for item in s:
         item = item.as_dict()
         if str(item['datetime']) not in export:
              export[str(item['datetime'])] = {}
         export[str(item['datetime'])][item['regionid']] = item
               
    return flask.jsonify(results=export)

@app.route("/update")
def update():
    s = session.query(dispatchIS).filter(dispatchIS.datetime > datetime.now() - timedelta(hours=1))
    export = {}
    for item in s:
         item = item.as_dict()
         if str(item['datetime']) not in export:
              export[str(item['datetime'])] = {}
         export[str(item['datetime'])][item['regionid']] = item
               
    return flask.jsonify(update=export)

@app.route("/interconnect-update")
def interconnectupdate():
    s = session.query(interconnect).filter(interconnect.datetime > datetime.now() - timedelta(hours=1))
    export = {}
    for item in s:
         item = item.as_dict()
         if str(item['datetime']) not in export:
              export[str(item['datetime'])] = {}
         export[str(item['datetime'])][item['interconnectorid']] = item
               
    return flask.jsonify(update=export)

	
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=9999)
