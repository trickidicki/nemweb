from flask import Flask, render_template 
from sqlalchemy.orm import sessionmaker 
from datetime import timedelta, datetime
import flask 
import urllib.request
import urllib.parse
from io import BytesIO 
import re 
import configparser
from flask_compress import Compress
import os
from pathlib import Path
from classdefs import *

#nem works on Brisbane time
os.environ['TZ'] = 'Australia/Brisbane'

compress = Compress()

config = configparser.ConfigParser()
config.read("config.cfg")

webconfig = config["webserver"]
 
app = Flask(__name__) 
dbg = webconfig.getboolean('debug', False)
app.debug = dbg
Compress(app)

engine = create_engine(config["database"]["dbstring"], pool_recycle=3600)  
  
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, autocommit=True)
session = Session()

def dictfetchall(cursor):
    # Returns all rows from a cursor as a list of dicts
    desc = cursor.description
    return [dict(zip([col[0] for col in desc], row)) 
            for row in cursor.fetchall()]

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/map")
def map():
    return render_template('map.html')

@app.route("/stations")
def stations():
    return render_template('stations.html')

@app.route("/station_overview")
def station_overview():
    return render_template('station_overview.html')

@app.route("/env")
def env():
    return render_template('env.html')

@app.route("/history")
def history():
    return render_template('historic.html')

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
    s = session.query(CO2Factor).filter(CO2Factor.ReportDate == session.query(func.max(CO2Factor.ReportDate)))
    for item in s:
         item = item.as_dict()
         export[item['DUID']] = item  
    return flask.jsonify(results=export)

@app.route("/station-history/<duid>")
def stationhistory(duid):
    duid = duid.replace("-slash-","/")
    s = session.query(DispatchSCADA).filter(DispatchSCADA.SETTLEMENTDATE > datetime.now() - timedelta(hours=128)).filter(DispatchSCADA.DUID == duid)
    export = {}
    for item in s:
         item = item.as_dict()
         export[str(item['SETTLEMENTDATE'])]=item
    return flask.jsonify(results=export)

@app.route("/stations-now")
def stationsnow():
    s = session.query(DispatchSCADA).filter(DispatchSCADA.SETTLEMENTDATE > datetime.now() - timedelta(hours=3))
    export = {}
    for item in s:
         item = item.as_dict()
         if item['DUID'] not in export:
             export[item['DUID']] = []
         export[item['DUID']].append(item)
    return flask.jsonify(results=export)


@app.route("/scada")
def scada():
    export = {}
    r = session.query(func.max(DispatchSCADA.SETTLEMENTDATE))[0][0]
    z = session.query(func.max(CO2Factor.ReportDate))[0][0]
    print(r)
    print(type(r))
    s = session.query(DispatchSCADA, CO2Factor.Factor).join(CO2Factor).filter(DispatchSCADA.SETTLEMENTDATE == r  ).filter(CO2Factor.ReportDate == z)
    for item in s:
         co2 = item[1]
         item = item[0].as_dict()
         try:
              item['CO2E'] = co2 * item['SCADAVALUE']
         except:
             pass
         item['SETTLEMENTDATE'] = str(item['SETTLEMENTDATE'])
         export[item['DUID']]=item
    return flask.jsonify(results=export)

@app.route("/historic")
def historic():
    s = engine.execute("select `datetime`, `regionid`, avg(rrp), max(rrp), min(rrp), avg(demand), max(demand), min(demand),"
                       "avg(generation), max(generation), min(generation) from dispatchIS "
                      #"GROUP BY HOUR(`datetime`),DAY(`datetime`),MONTH(`datetime`),YEAR(`datetime`), regionid;")
                      "GROUP BY "
                      "strftime('%H',`datetime`), "
                      "strftime('%dT',`datetime`), "
                      "strftime('%m',`datetime`), "
                      "strftime('%Y',`datetime`), "
                      "regionid;")
    export = {}
    for item in s:
        item = dict(item.items())
        if str(item['datetime']) not in export:
             export[str(item['datetime'])] = {}
        export[str(item['datetime'])][item['regionid']] = item
    return flask.jsonify(results=export)

@app.route("/dispatch")
def dispatch():
    s = session.query(dispatchIS).filter(dispatchIS.datetime > datetime.now() - timedelta(hours=168))
    export = {}
    for item in s:
         item = item.as_dict()
         if str(item['datetime']) not in export:
              export[str(item['datetime'])] = {}
         export[str(item['datetime'])][item['regionid']] = item
               
    return flask.jsonify(results=export)

@app.route("/interconnect")
def interconnectjson():
    s = session.query(interconnect).filter(interconnect.datetime > datetime.now() - timedelta(hours=24))
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
    extra_dirs = ['templates','static',]
    extra_files = extra_dirs[:]
    for extra_dir in extra_dirs:
        for filename in Path(extra_dir).glob("**/*.*"):
            if Path.is_file(filename):
                extra_files.append(filename)
                print("Watching %s for changes" % (filename))
    app.run(extra_files=extra_files, host=webconfig.get("host", "0.0.0.0"), port=webconfig.getint("port", 5000))
