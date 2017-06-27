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
from sqlalchemy.orm import sessionmaker
from zipfile import ZipFile
from pathlib import PurePath, Path
from urllib.parse import urlparse
import csv
import argparse
import pandas as pd
from classdefs import *

config = configparser.ConfigParser()
config.read("config.cfg")

urls = {
	"base": "http://www.nemweb.com.au/",
	"p5": "http://www.nemweb.com.au/Reports/CURRENT/P5_Reports/",
	"dispatchis": "http://www.nemweb.com.au/Reports/CURRENT/DispatchIS_Reports/",
	"scada": "http://www.nemweb.com.au/Reports/CURRENT/Dispatch_SCADA/",
    "co2": "http://www.nemweb.com.au/reports/current/cdeii/",
    "stations": "https://www.aemo.com.au/-/media/Files/Electricity/NEM/Participant_Information/Current-Participants/NEM-Registration-and-Exemption-List.xls"
}

engine = create_engine(config["database"]["dbstring"])
        
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
    def get_str(item):
        return str(item).strip()
    try:
        #localdata = config["localdata"]
        #csvfilelocation = localdata.get("stations", "stations.csv")
        #fileexists = Path(csvfilelocation).is_file()
        #with open(csvfilelocation) as csvfile:
        data_xls = pd.read_excel(urls['stations'], 'Generators and Scheduled Loads')
        for index, row  in data_xls.iterrows():
            if(len(row) < 18):
                continue
            if row["DUID"] == '-':
                continue
            print(row["DUID"])
            if str(row["Reg Cap (MW)"]).strip() in ['-', '_']:
                row["Reg Cap (MW)"] = 0
            station = {
                "DUID": row["DUID"].strip(),
                "regionid": row["Region"].strip(),
                "regcap": mk_zero(row["Reg Cap (MW)"]),
                "FuelSource": get_str(row["Fuel Source - Primary"]),
                "FuelSourceDescriptior": get_str(row["Fuel Source - Descriptor"]),
                "Tech": get_str(row["Technology Type - Primary"]),
                "TechDescription": get_str(row["Technology Type - Descriptor"]),
                "Participant": get_str(row["Participant"]),
                "StationName": get_str(row["Station Name"])
                }
            stationobject = stationdata(**station)
            session.merge(stationobject)
            session.commit()

    except Exception as e:
        print(traceback.format_exc())

    print("Done")

def doProcess(func):
    print("Processing " + func.__name__ )
    func()
    print("Done")

argparser = argparse.ArgumentParser()
argparser.add_argument('-s', '--stations', help='Process stations list', action='store_true')
args = argparser.parse_args()

if args.stations:
    processStations()
else:
    try:
        #doProcess(processStations)
        doProcess(processCO2)
        doProcess(processP5)
        doProcess(processDispatchIS)
        doProcess(processSCADA)
        #time.sleep(30)
    except Exception as e:
        print(traceback.format_exc())
