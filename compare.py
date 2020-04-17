import os
import re
from flask import Flask, render_template, flash
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField,TextAreaField
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
    
    def graphInit(self):
        graph = rdflib.Graph()
        
    def error(self,mess):
        self.graphInit()
        flash(mess)
        
    def compare(self):
        form = CompareSelectForm()
        dataToDisplay = False
        self.source = form.source.data
        self.sourceType = form.sourceType.data
        self.sourceFormat = form.sourceFormat.data
        self.outFormat = form.outFormat.data
        
        if self.sourceType.startswith('http'):  # A sample file!!
            form.source.data = self.source = self.sourceType
            form.sourceType.data = self.sourceType = 'url'
        
        if self.source:
            
            self.getSource() #Go get input
            
            if len(self.graph): #We got some input
                try:
                    self.dataSource = self.graph.serialize(format = self.outFormat , auto_compact=True).decode('utf-8')
                    if self.outFormat == "jsonld":
                        self.dataSource = self.simplyframe(self.dataSource)
                
                    if self.process():
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

        return render_template('compare.html',
                                title='Compare Schema',
                                form=form,
                                dataSource = self.dataSource,
                                dataFull = self.dataFull,
                                dataSchema = self.dataSchema,
                                diplaylang = self.outFormat,
                                dataToDisplay = dataToDisplay)
    
    def getSource(self):
        self.graphInit()
 
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
            
        self.check4Bibframe()

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
        except Exception as e:
            print("Error parsing returned LoC record: %s" % e)
            self.error("Error parsing returned LoC record: %s" % e)
    
    def check4Bibframe(self):
        res = self.graph.query(CHECK4BF)
        if not len(res):
            self.error("Bibframe Work, Instance, or Item not identified in source")


        
    def process(self):
        global SPARQLSCRIPT,TESTSPARQLSCRIPT
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
                    return True
                except Exception as e:
                    self.error("Sparql parse error: %s" % e)
                    print("Sparql parse error: \n%s" % (e))
        return False
        
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
                

class CompareSelectForm(FlaskForm):
    source = StringField('Source')
    submit = SubmitField('Search')
    sourceType = SelectField('Source Type', choices=[('url','URL'),
                                ('locbib','LoC Bib ID'),
                                ('loclccn','LoC LCCN'),
                                ('https://raw.githubusercontent.com/RichardWallis/bibframe2schema/master/tests/source/LCCN-98033893.xml','Sample Source')])
    sourceFormat = SelectField('Source Format', choices=[('auto','auto'),('xml','RDF/XML'),('jsonld','JSON-LD'),('turtle','Turtle')])
    outFormat = SelectField('Disply Format', choices=[('jsonld','JSON-LD'),('xml','RDF/XML'),('turtle','Turtle')])
    
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

    