import urllib.request
import configparser
import csv
import sqlalchemy
import json
import traceback
import time
from bs4 import BeautifulSoup
from datetime import datetime
from html.parser import HTMLParser
from io import BytesIO, TextIOWrapper
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from zipfile import ZipFile
from pathlib import PurePath, Path
from urllib.parse import urlparse
import csv

config = configparser.ConfigParser()
config.read("config.cfg")

urls = {
	"base": "http://www.nemweb.com.au/",
	"p5": "http://www.nemweb.com.au/Reports/CURRENT/P5_Reports/",
	"dispatchis": "http://www.nemweb.com.au/Reports/CURRENT/DispatchIS_Reports/",
	"notices": "http://www.nemweb.com.au/Reports/CURRENT/Market_Notice/",
	"scada": "http://www.nemweb.com.au/Reports/CURRENT/Dispatch_SCADA/",
    "co2": "http://www.nemweb.com.au/reports/current/cdeii/"
}

engine = create_engine(config["database"]["dbstring"])
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

class dispatchIS(Base):
     __tablename__ = 'dispatchIS'
     datetime = Column(DateTime, primary_key=True)
     regionid = Column(String(100), primary_key=True)
     rrp = Column(Float)
     demand = Column(Float)
     generation = Column(Float)

class interconnect(Base):
     __tablename__ = 'interconnect-dispatchIS'
     datetime = Column(DateTime, primary_key=True)
     interconnectorid = Column(String(100), primary_key=True)
     meteredmwflow = Column(Float)
     mwflow = Column(Float)
     mwlosses = Column(Float)
     exportlimit = Column(Float)
     importlimit = Column(Float)

class notices(Base):
     __tablename__ = 'notices'
     id = Column(Integer, primary_key=True)
     datetime = Column(DateTime)
     message = Column(String(500))
     url = Column(String(255))
class DUID(Base):
     __tablename__ = 'duid'
     id = Column(String(255), primary_key=True)
     twitter = Column(String(255))
      
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

class DispatchSCADA(Base):
     __tablename__ = 'DispatchSCADA'
     DUID = Column(String(255), primary_key=True)
     SETTLEMENTDATE = Column(DateTime, primary_key=True)
     SCADAVALUE = Column(Float)

class CO2Factor(Base):
     __tablename__ = 'CO2Factor'
     DUID = Column(String(255), primary_key=True)
     ReportDate = Column(DateTime, primary_key=True)
     Factor = Column(Float)
        
Base.metadata.create_all(engine) 
Session = sessionmaker(bind=engine)
session = Session()

def urlDownloaded(url):
    if session.query(Downloads.url).filter(Downloads.url==urls['base'] +url).count() > 0:
        return True
    else:
        return False

def downloadUrl(url):
    parse = urlparse(url)
    print("Downloading " + parse.scheme + "://" + parse.hostname + "/.../" + PurePath(parse.path).name, end='\r', flush = True)
    return urllib.request.urlopen(url).read()

def listFiles(url, requiredFilenameString = None):
    pageurls=[]
    indexpage = downloadUrl(url)
    soup = BeautifulSoup(indexpage, "html.parser")
    for link in soup.find_all('a'):
        url = link.get('href')
        parts = PurePath(url)
        if not parts.suffix:
            continue
        if requiredFilenameString:
            if requiredFilenameString not in parts.stem:
                continue
        if parts.suffix.lower() in [".zip", ".csv"]:
            if urlDownloaded(url) == False:
                pageurls.append(urls['base'] + url)
    return pageurls

def listCO2Files():
    return listFiles(urls['co2'], "CO2EII_AVAILABLE_GENERATORS")

def processCO2():
    urls = listCO2Files()
    for url in urls:
        try:
                data = downloadUrl(url)
                data = data.decode('utf-8').split("\n")
                csvfile = csv.reader(data)
                date = ""
                time = ""
                for row in csvfile:
                        try:
                                if row[0] == "I" and row[1] == "CO2EII" and row[2] == "PUBLISHING":
                                        columns = row
                                elif row[2] == "CO2EII_AVAILABLE_GENERATORS":
                                        date = row[5]
                                        time = row[6]
                                elif row[2] == "PUBLISHING":
                                        co2value = {
                               "ReportDate" : datetime.strptime(date + " " + time, "%Y/%m/%d %H:%M:%S"),
                               "DUID" : row[columns.index("DUID")],
                               "Factor" : row[columns.index("CO2E_EMISSIONS_FACTOR")]
                               }
                                        co2dbobject = CO2Factor(**co2value)
                                        session.merge(co2dbobject)
                        except(IndexError):
                                pass
                session.merge(Downloads(url=url))
                session.commit()
        except Exception as e:
            session.merge(Downloads(url=url))
            session.commit()
            print(traceback.format_exc())


#returns list of P5 files as an array of urls
def listP5Files():
     return listFiles(urls['p5'])

def processP5():
    for url in listP5Files():
        try:
                files = ZipFile(BytesIO(downloadUrl(url)))
                data = files.read(files.namelist()[0])
                data = data.decode('utf-8').split("\n")
                csvfile = csv.reader(data)
                for row in csvfile:
                        try:
                                if row[0] == "I" and row[1] == "P5MIN" and row[2] == "REGIONSOLUTION":
                                        columns = row
                                elif row[2] == "REGIONSOLUTION":
                                        p5value = {
                               "datetime" : datetime.strptime(row[columns.index("INTERVAL_DATETIME")], "%Y/%m/%d %H:%M:%S"),
                               "regionid" : row[columns.index("REGIONID")],
                               "rrp" : row[columns.index("RRP")],
                               "demand" : row[columns.index("TOTALDEMAND")],
                               "generation" : row[columns.index("AVAILABLEGENERATION")] 
                               }
                                        p5dbobject = P5(**p5value)
                                        session.merge(p5dbobject)
                        except(IndexError):
                                pass
                session.merge(Downloads(url=url))
                session.commit()
        except Exception as e:
            session.merge(Downloads(url=url))
            session.commit()
            print(traceback.format_exc())
        
def listDispatchISFiles():
    return listFiles(urls['dispatchis'])
    
def processDispatchIS():
    for url in listDispatchISFiles():
        try:
                files = ZipFile(BytesIO(downloadUrl(url)))
                data = files.read(files.namelist()[0])
                data = data.decode('utf-8').split("\n")
                csvfile = csv.reader(data)
                for row in csvfile:
                    try:
                        if row[0] == "I" and row[1] == "DISPATCH" and row[2] == "PRICE":
                                    columnsprice = row
                        elif row[2] == "PRICE":
                                    dispatchISvalue = {
                               "datetime" : datetime.strptime(row[columnsprice.index("SETTLEMENTDATE")],"%Y/%m/%d %H:%M:%S"),
                               "regionid" : row[columnsprice.index("REGIONID")],
                               "rrp" : row[columnsprice.index("RRP")]
                               }
                                    dispatchISobject = dispatchIS(**dispatchISvalue)
                                    session.merge(dispatchISobject)
                        elif row[0] == "I" and row[1] == "DISPATCH" and row[2] == "REGIONSUM":
                                    columnsdemand = row
                        elif row[2] == "REGIONSUM":
                                    dispatchISvalue = {
                               "datetime" : datetime.strptime(row[columnsdemand.index("SETTLEMENTDATE")],"%Y/%m/%d %H:%M:%S"),
                               "regionid" : row[columnsdemand.index("REGIONID")],
                               "demand" : row[columnsdemand.index("TOTALDEMAND")],
                               "generation" : row[columnsdemand.index("AVAILABLEGENERATION")] 
                               }
                                    dispatchISobject = dispatchIS(**dispatchISvalue)
                                    session.merge(dispatchISobject)
                        elif row[0] == "I" and row[1] == "DISPATCH" and row[2] == "INTERCONNECTORRES":
                                    columnsinterconnect = row
                        elif row[2] == "INTERCONNECTORRES":
                                    interconnectvalue = {
                               "datetime" : datetime.strptime(row[columnsinterconnect.index("SETTLEMENTDATE")],"%Y/%m/%d %H:%M:%S"),
                               "interconnectorid" : row[columnsinterconnect.index("INTERCONNECTORID")],
                               "meteredmwflow" : row[columnsinterconnect.index("METEREDMWFLOW")],
                               "mwflow" : row[columnsinterconnect.index("MWFLOW")] ,
                               "mwlosses" : row[columnsinterconnect.index("MWLOSSES")] ,
                               "exportlimit" : row[columnsinterconnect.index("EXPORTLIMIT")] ,
                               "importlimit" : row[columnsinterconnect.index("IMPORTLIMIT")] 
                               }
                                    interconnectobject = interconnect(**interconnectvalue)
                                    session.merge(interconnectobject)
                    except(IndexError):
                        pass
                session.merge(Downloads(url=url))
                session.commit()
        except Exception as e:
            session.merge(Downloads(url=url))
            session.commit()
            print(traceback.format_exc())

#returns list of P5 files as an array of urls
def listNotices():
    raise NotImplementedError('Check how / is handled') 
    return listFiles(urls['notices'])

def processNotices():
    for url in listNotices():
        try:
            data = downloadUrl(url).decode('iso-8859-1','ignore')
            data = data.split("\n")
            amount = ""
            for line in data:
                if "Creation Date" in line:
                    date = line.split(":",1)[-1].strip()
                elif "Notice ID" in line:
                    id = int(line.split(":",1)[-1].strip())
                elif "External Reference" in line:
                    notice = line.split(":",1)[-1].strip()
                    notice = notice.replace("Reclassification ","#reclass ")
                    notice = notice.replace("Non-Credible ","#non_cred ")
                    notice = notice.replace("Event ","evnt ")
                    notice = notice.replace("Queensland ","qld ")
                    notice = notice.replace("Cancellation ","#cancel ")
                    notice = notice.replace("Contingency ","#contigency ")
                    notice = notice.replace("Cessation ","#cease ")
                    notice = notice.replace("Revision ","#revise ")
                    notice = notice.replace("Region "," ")
                elif "Constraint:" in line:
                    constraint = line.split(":",1)[-1].strip()
                    constraint = constraint.replace("-", "_")
                    if amount:
                        notice = "#" + constraint + " " + amount + " - " + notice
                    else:
                        notice = "#" + constraint + " - " + notice
                elif "Unit:" in line:
                    unit = line.split(":",1)[-1].strip()
                    twitterhandles = session.query(DUID).filter(DUID.id==unit)
                    for handle in twitterhandles:
                        notice = "@" + handle.twitter  +" " +notice
                elif "Amount:" in line:
                    amount = line.split(":",1)[-1].strip()
            urlviewer=url.replace("http://www.nemweb.com.au/Reports/CURRENT/Market_Notice/","http://nem.mwheeler.org/notice/")
            sendTwit(notice[:110] + "... " + urlviewer)
            msgtime = datetime.strptime(date,'%d/%m/%Y     %H:%M:%S')
            session.merge(notices(id=id, datetime=msgtime, message=notice, url=url))
            session.merge(Downloads(url=url))
            session.commit()
        except Exception as e:
            session.merge(Downloads(url=url))
            session.commit()
            print(traceback.format_exc())

def listSCADAFiles():
    return listFiles(urls['scada'])

def processSCADA():
    for url in listSCADAFiles():
        try:
                files = ZipFile(BytesIO(downloadUrl(url)))
                data = files.read(files.namelist()[0])
                data = data.decode('utf-8').split("\n")
                csvfile = csv.reader(data)
                for row in csvfile:
                        try:
                                if row[0] == "I" and row[1] == "DISPATCH" and row[2] == "UNIT_SCADA":
                                        columns = row
                                elif row[2] == "UNIT_SCADA":
                                        scadavalue = {
                               "SETTLEMENTDATE" : datetime.strptime(row[columns.index("SETTLEMENTDATE")], "%Y/%m/%d %H:%M:%S"),
                               "DUID" : row[columns.index("DUID")],
                               "SCADAVALUE" : row[columns.index("SCADAVALUE")]
                               }
                                        scadadbobject = DispatchSCADA(**scadavalue)
                                        session.merge(scadadbobject)
                        except(IndexError):
                                pass
                session.merge(Downloads(url=url))
                session.commit()
        except Exception as e:
            session.merge(Downloads(url=url))
            session.commit()
            print(traceback.format_exc())

def processStations():
    def mk_zero(s):
        s = str(s).strip()
        return s if s else "0"
    try:
        localdata = config["localdata"]
        csvfilelocation = localdata.get("stations", "stations.csv")
        fileexists = Path(csvfilelocation).is_file()
        with open(csvfilelocation) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row["DUID"] == '-':
                    continue
                print(row["DUID"])
                if row["Reg Cap (MW)"].strip() in ['-', '_']:
                    row["Reg Cap (MW)"] = 0
                station = {
                    "DUID": row["DUID"].strip(),
                    "regcap": mk_zero(row["Reg Cap (MW)"]),
                    "FuelSource": row["Fuel Source - Primary"].strip(),
                    "FuelSourceDescriptior": row["Fuel Source - Descriptor"].strip(),
                    "Tech": row["Technology Type - Primary"].strip(),
                    "TechDescription": row["Technology Type - Descriptor"].strip(),
                    "Participant": row["Participant"].strip(),
                    "StationName": row["Station Name"].strip()
                    }
                stationobject = stationdata(**station)
                session.merge(stationobject)
                session.commit()

    except Exception as e:
        print(traceback.format_exc())

def doProcess(func):
    print("Processing " + func.__name__ )
    func()
    print("Done")

        
try:
    doProcess(processStations)
    doProcess(processCO2)
    doProcess(processP5)
    doProcess(processDispatchIS)
    doProcess(processSCADA)
    doProcess(processNotices)
    #time.sleep(30)
except Exception as e:
    print(traceback.format_exc())
