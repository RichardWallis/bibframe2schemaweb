import logging
logging.basicConfig(level=logging.INFO) # dev_appserver.py --log_level debug .
log = logging.getLogger(__name__)

import os
import re
from flask import Flask, render_template, flash, request
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField,TextAreaField
from flask_wtf.file import  FileField, FileAllowed, FileRequired
from werkzeug.utils import secure_filename
from urllib.request import urlopen
from urllib.parse import urlparse
import xml.dom.minidom

import json
import rdflib
import rdflib_jsonld
from rdflib.parser import Parser
from rdflib.serializer import Serializer

rdflib.plugin.register("jsonld", Parser, "rdflib_jsonld.parser", "JsonLDParser")
rdflib.plugin.register("jsonld", Serializer, "rdflib_jsonld.serializer", "JsonLDSerializer")

import config

UPLOADTYPES = {'jsonld': 'jsonld','xml':'xml'}
UPLOADTYPES.update(rdflib.util.SUFFIX_FORMAT_MAP)

FLATTENIDS = True
TESTTOKENFILE= "file:./testtokens.json"
#TESTTOKENFILE= "file:////Users/wallisr/Development/bibframe2schema/bibframe2schemaweb/testtokens.json"
TOKENFILE= "https://github.com/RichardWallis/bibframe2schema/raw/master/tokens.json"
TOKENS = None
TESTSPARQLSCRIPT = "file:./testbibframe2schema.sparql"
#TESTSPARQLSCRIPT = "file:////Users/wallisr/Development/bibframe2schema/bibframe2schemaweb/testbibframe2schema.sparql"
SPARQLSCRIPT = "https://raw.githubusercontent.com/RichardWallis/bibframe2schema/master/query/bibframe2schema.sparql"

SCHEMAONLY="""
prefix schema: <http://schema.org/> 
DELETE {
    ?s ?p ?o.
} WHERE {
    ?s ?p ?o.
    FILTER ( ! (strstarts(str(?p),"http://schema.org") || strstarts(str(?o),"http://schema.org")) )
}"""

CHECK4BF = """
SELECT * WHERE {
    {
        ?s a <http://id.loc.gov/ontologies/bibframe/Work> .
    } UNION {
        ?s a <http://id.loc.gov/ontologies/bibframe/Instance> .
    } UNION {
        ?s a <http://id.loc.gov/ontologies/bibframe/Item> .
    }
}"""

class Compare():
    graph = rdflib.Graph()
    source = None
    sourctType = None
    sourceFormat = None
    outFormat = None
    dataSource = None
    dataFull = None
    dataSchema = None
    sampleFile = False
    gotSource = False
    gotBf = False
    processed = False
    action=""
    outputFormat=""
    akLoC = False
    
    
    def graphInit(self):
        self.graph = rdflib.Graph()

    def error(self,mess):
        self.graphInit()
        flash(mess)
        
    def compare(self):
        dataToDisplay = False
        self.graphInit()
        self.dataSource = self.dataFull = self.dataSchema = None
        self.form = CompareSelectForm()
        self.pasteForm = PasteSelectForm()
        self.uploadForm = UploadSelectForm()
        self.inputSelect = ""
        if not self.loadSourceInputs():
            if not self.loadPasteInputs():
                if not self.loadUploadInputs():
                    self.graphInit()
        

        if len(self.graph): #We got some input
            self.gotSource = True
            try:
                self.dataSource = self.graph.serialize(format = self.outFormat , auto_compact=True).decode('utf-8')
                print
                if self.outFormat == "jsonld":
                    self.dataSource = self.simplyframe(self.dataSource)

                if self.process():
                    self.processed = True
                    self.dataFull = self.graph.serialize(format = self.outFormat , auto_compact=True).decode('utf-8')
                    if self.outFormat == "jsonld":
                        self.dataFull = self.simplyframe(self.dataFull)

                    if self.schemaOnly():
                        context = {"schema": "http://schema.org/" }
                        self.dataSchema = self.graph.serialize(format = self.outFormat ,
                                        context = context,
                                        auto_compact=True,
                                        sort_keys=True).decode('utf-8')
                        
                        if self.outFormat == "jsonld":
                            self.dataSchema = self.simplyframe(self.dataSchema)

            except Exception as e:
                print("Output serialization error: %s" % e)
                self.error("Output serialization error: %s" % e)

            if self.dataSource or self.dataFull or self.dataSchema:
                dataToDisplay = True
            #print("%s %s %s" % (len(self.dataSource),len(self.dataFull),len(self.dataSchema)))
            self.logRequest()

        return render_template('compare.html',
                                title='Compare Schema',
                                form=self.form,
                                pasteForm=self.pasteForm,
                                uploadForm=self.uploadForm,
                                dataSource = self.dataSource,
                                inputSelect = self.inputSelect,
                                dataFull = self.dataFull,
                                dataSchema = self.dataSchema,
                                diplaylang = self.outFormat,
                                dataToDisplay = dataToDisplay,
                                scriptUsed = SPARQLSCRIPT,
                                akLoC = self.akLoC)
    
    def loadSourceInputs(self):
        loaded = False
        if self.form.submit.data:
            self.inputSelect = "search"
            self.source = self.form.source.data
            self.sourceType = self.form.sourceType.data
            self.sourceFormat = self.form.sourceFormat.data
            self.outputFormat = self.outFormat = self.form.outFormat.data
        
            if self.sourceType.startswith('http'):  # A sample file!!
                self.sampleFile = True
                self.form.source.data = self.source = self.sourceType
                self.form.sourceType.data = self.sourceType = 'url'
        
            if self.source:
                self.getSource() #Go get input

            if len(self.graph):
                loaded = True
        return loaded
        
    def loadPasteInputs(self):
        loaded = False
        action = "paste"
        if self.pasteForm.pasteSubmit.data:
            self.inputSelect = "paste"
            data = self.pasteForm.pasteSource.data
            data = data.strip()
            self.sourceFormat = self.pasteForm.pasteSourceFormat.data
            self.outputFormat = self.outFormat = self.pasteForm.pasteOutFormat.data
            if self.sourceFormat == "auto":
                if data.startswith("<?xml version="):
                    self.sourceFormat = "xml"
                elif "@context" in data:
                    self.sourceFormat = "jsonld"
                elif "@id" in data:
                    self.sourceFormat = "jsonld"
                elif "@type" in data:
                    self.sourceFormat = "jsonld"
                elif "@prefix" in data:
                    self.sourceFormat = "turtle"
                elif "<http:" in data:
                    self.sourceFormat = "turtle"
                elif "<https:" in data:
                    self.sourceFormat = "turtle"

            if self.sourceFormat == "xml":
                doc = None
                try:
                    doc = xml.dom.minidom.parseString(data)
                except Exception as e:
                    self.error("XML Parse error: %s" % e)

                rdfnodes = doc.getElementsByTagNameNS("http://www.w3.org/1999/02/22-rdf-syntax-ns#","RDF")
                if len(rdfnodes) == 1:
                    bf = rdfnodes[0].toxml()
                    try:
                        self.graph.parse(data=bf, format='xml')
                    except Exception as e:
                        self.error("Error parsing RDF: %s" % e)
                else:
                    self.error("RDF Parse error number of RDF nodes identified: %s - should only be 1" % len(rnodes) )
                    
            elif self.sourceFormat == "jsonld":
                try:
                    self.graph.parse(data=data, format='jsonld')
                except Exception as e:
                    self.error("Error parsing jsonld: %s" % e)

            elif self.sourceFormat == "turtle":
                try:
                    self.graph.parse(data=data, format='turtle')
                except Exception as e:
                    self.error("Error parsing turtle: %s" % e)


            if len(self.graph):
                loaded = True

        return loaded

    def loadUploadInputs(self):
        global UPLOADTYPES
        loaded = False
        action = "upload"
        if self.uploadForm.uploadSubmit.data: 
            self.inputSelect = "upload"
            self.outputFormat = self.outFormat = self.uploadForm.uploadOutFormat.data
            if self.uploadForm.validate_on_submit():
                f = self.uploadForm.uploadFile.data
                filename = secure_filename(f.filename)
                data = f.read()
                data = data.strip()
                ext = os.path.splitext(filename)[1]
                ext = ext[1:]
                format = UPLOADTYPES.get(ext,None)
                if format :
                    try:
                        self.graph.parse(data=data, format=format) 
                    except Exception as e:
                        print("Error parsing uploaded file: %s" % e)
                        self.error("Error parsing uploaded file: %s" % e)

            if len(self.graph):
                loaded = True

        return loaded
            
    def getSource(self):
        self.graphInit()
        self.action = self.sourceType
        sformat = self.sourceFormat
        if sformat == 'auto':
            sformat = None
            ext = os.path.splitext(self.source)[1]
            if ext:
                sformat = ext[1:]
                
        if self.sourceType == 'url':
            isUrl = False
            u = urlparse(self.source)
            if u.scheme and u.netloc:
                isUrl = True
            if not isUrl:
                self.error("Not a valid URL")
                return
            
            try:
                if sformat:
                    self.graph.parse(source=self.source, format=sformat)
                else:
                    self.graph.parse(source=self.source)
            except Exception as e:
                print("RDF Parse error: %s" % e)
                self.error("Error no identifiable rdf returned: %s" % e)
                
        elif self.sourceType == 'locbib' or self.sourceType == 'loclccn':
            self.getLoc(self.sourceType,self.source)
            

    def getLoc(self,qtype,id):
        bf=None
        if qtype == "locbib":
            insert = 'rec.id={id}'.format(id=id)
        else:
            insert ='bath.lccn=%22%5E{id}$%22'.format(id=id)
        url="http://lx2.loc.gov:210/LCDB?query={insert}&recordSchema=bibframe2a&maximumRecords=1".format(insert=insert)
        
        try:
            doc = xml.dom.minidom.parse(urlopen(url))
            
            count = doc.getElementsByTagNameNS("http://docs.oasis-open.org/ns/search-ws/sruResponse","numberOfRecords")[0].childNodes[0].nodeValue
            if count != "1":
                self.error("Error '%s' records returned from LoC" % count)
                return
            
            rdfnodes = doc.getElementsByTagNameNS("http://www.w3.org/1999/02/22-rdf-syntax-ns#","RDF")
            if not rdfnodes:
                self.error("LoC Record load error: Cannot identify RDF:rdf node in respose")
                print("LoCSRUResponse - XML Load error: Cannot identify <rdf:RDF> node in response")
                return
            else:
                bf = rdfnodes[0].toxml()
        except Exception as e:
            print("LoCSRUResponse - XML Load error: %s" % e)
            self.error("Error retreving LoC record: %s" % e)
            
        try:
            self.graph.parse(data=bf, format='xml')
            self.akLoC = True
        except Exception as e:
            print("Error parsing returned LoC record: %s" % e)
            self.error("Error parsing returned LoC record: %s" % e)
    
    def check4Bibframe(self):
        res = self.graph.query(CHECK4BF)
        if not len(res):
            self.gotBf = False
            self.error("Bibframe Work, Instance, or Item not identified in source")
        else:
            self.gotBf = True
        return self.gotBf


        
    def process(self):
        global SPARQLSCRIPT,TESTSPARQLSCRIPT
        ret = False
        if self.check4Bibframe():   #Found some bibframe entities     
            script = SPARQLSCRIPT
            if config.TestMode:
                script = TESTSPARQLSCRIPT
            
            sparql = URLCache.get(script)
            if sparql:
                sparql = self.tokenSubstitute(sparql)
                if sparql:
                    try:
                        self.graph.bind('schema', 'http://schema.org/')
                        self.graph.update(sparql)
                        ret = True
                    except Exception as e:
                        self.error("Sparql parse error: %s" % e)
                        print("Sparql parse error: \n%s" % (e))
        return ret
        
    def schemaOnly(self):
        global SCHEMAONLY
        try:
            self.graph.update(SCHEMAONLY)
            return True
        except Exception as e:
            print("SchemaOnly sparql parse error: \n%s" % (e))
        return False
    
    def tokenSubstitute(self,string):
        global TOKENFILE,TESTTOKENFILE,TOKENS
    
        if not TOKENS:
            today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
            now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            TOKENS = {
                "TODAY": today,
                "NOW": now
            }

            data = None
            tfile = TOKENFILE
            if config.TestMode:
                tfile = TESTTOKENFILE
                
            if tfile:
                try:
                    tf = URLCache.get(tfile)
                    if tf:
                        data = json.loads(tf)
                except Exception as e:
                     print("Token file load error: \n%s" % (e))
                     self.error("Token file load error: \n%s" % (e))
                     return None
 
            if data:
                TOKENS.update(data)

        if TOKENS:
            for t, v in TOKENS.items():
                string = string.replace("[[%s]]" % t ,v)
        
        string = re.sub('\\[\\[.*?\\]\\]','',string) #Remove unrecognised tokens
        
        return string
    
    def simplyframe(self,jsl):
        data = json.loads(jsl)
        items, refs = {}, {}
        for item in data['@graph']:
            itemid = item.get('@id')
            if itemid:
                items[itemid] = item
            for vs in item.values():
                for v in [vs] if not isinstance(vs, list) else vs:
                    if isinstance(v, dict):
                        refid = v.get('@id')
                        if refid and refid.startswith('_:'):
                            refs.setdefault(refid, (v, []))[1].append(item)
        for ref, subjects in refs.values():
            if len(subjects) == 1:
                ref.update(items.pop(ref['@id']))
                del ref['@id']
        if FLATTENIDS:
            items = self.flattenIds(items)
        data['@graph'] = items
        return json.dumps(data, indent=2)
        
    def flattenIds(self, node):
        ret = node
        if isinstance(node, dict):
            if len(node) == 1:
                id = node.get("@id", None)
                if id:
                    return id #Return node @id instead of node
            for s, v in node.items():
                node[s] = self.flattenIds(v)

        elif isinstance(node,list):
            lst = []
            for v in node:
                lst.append(self.flattenIds(v))
            ret = lst
        return ret
        
    def flush(self):
        URLCache.flush()
        flash("URLCache flushed")
        
    def logRequest(self):
        if request.method == 'POST':
            caller = request.environ.get('HTTP_X_FORWARDED_FOR')
            if not caller:
                caller = request.environ.get('REMOTE_ADDR')
            stype = self.action
            source = self.source
            if self.sampleFile:
                stype = "Sample"
                source = ""
            oformat = self.outputFormat
            
            gs = gb = "No "
            pr = "Not "
            if self.gotSource:
                gs = ""
            if self.gotBf:
                gb = ""
            if self.processed:
                pr = ""
                
            dt = datetime.datetime.now()
            if dt.microsecond >= 500000:
                dt = dt + datetime.timedelta(seconds=1)
            dt = dt.replace(microsecond=0)
            
            
            log.info("%s - %s - %s - %s - %sSource %sBF %sProcessed" % (caller,
                                        stype,
                                        source,
                                        oformat,
                                        gs,
                                        gb,
                                        pr))
   
   
INTYPES = [('auto','auto'),('xml','RDF/XML'),('jsonld','JSON-LD'),('turtle','Turtle')]
OUTTYPES = [('jsonld','JSON-LD'),('xml','RDF/XML'),('turtle','Turtle')]             

class CompareSelectForm(FlaskForm):
    source = StringField('Source')
    submit = SubmitField('Search')
    sourceType = SelectField('Source Type', choices=[('url','URL'),
                                ('locbib','LoC Bib ID'),
                                ('loclccn','LoC LCCN'),
                                ('https://raw.githubusercontent.com/RichardWallis/bibframe2schema/master/tests/source/LCCN-98033893.xml','Sample Source')])
    sourceFormat = SelectField('Source Format', choices=INTYPES)
    outFormat = SelectField('Disply Format', choices=OUTTYPES)

class PasteSelectForm(FlaskForm):
    pasteSource = TextAreaField('Paste')
    pasteSubmit = SubmitField('Process')
    pasteSourceFormat = SelectField('Source Format', choices=INTYPES)
    pasteOutFormat = SelectField('Disply Format', choices=OUTTYPES)
    
class UploadSelectForm(FlaskForm):
    ftypes = ['jsonld']
    ftypes.extend(rdflib.util.SUFFIX_FORMAT_MAP.values())
    uploadFile = FileField(validators=[FileAllowed(ftypes, 'RDF only!'), FileRequired('File was empty!')])
    uploadSubmit = SubmitField('Upload')
    uploadOutFormat = SelectField('Disply Format', choices=OUTTYPES)
    
import datetime
import urllib.request

class URLCache():
    items = {}
    
    @classmethod
    def get(cls,url):
        itm = cls.items.get(url,None)
        if itm:
            timeout = datetime.timedelta(hours=1)
            if (itm.time + timeout) <  datetime.datetime.now():
                #print("Expired")
                itm = None

        if not itm:
            try:
                req = urllib.request.Request(url)
                data = urllib.request.urlopen(req).read()
                data = data.decode('utf-8')
                itm = item(data)
                cls.items[url] = itm
            except Exception as e:
                print("URL read error url '%s': \n%s" % (url,e))
                self.error("URL read error url '%s': \n%s" % (url,e))
                return None
        return itm.data

    @classmethod
    def flush(cls):
        cls.items = {}

class item():
    def __init__(self,data):
        self.data = data
        self.time = datetime.datetime.now()

    