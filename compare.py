import os
from flask import Flask, render_template, flash
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField,TextAreaField
from urllib.request import urlopen

import xml.dom.minidom

import json
import rdflib
import rdflib_jsonld
from rdflib.parser import Parser
from rdflib.serializer import Serializer

rdflib.plugin.register("jsonld", Parser, "rdflib_jsonld.parser", "JsonLDParser")
rdflib.plugin.register("jsonld", Serializer, "rdflib_jsonld.serializer", "JsonLDSerializer")

FLATTENIDS = True
TOKENFILE= "https://github.com/RichardWallis/bibframe2schema/raw/master/tokens.json"
TOKENS = None
SPARQLSCRIPT = "file:////Users/wallisr/Development/Biframe2Schema/bibframe2schemaweb/testbibframe2schema.sparql"
#SPARQLSCRIPT = "https://raw.githubusercontent.com/RichardWallis/bibframe2schema/master/query/bibframe2schema.sparql"
SCHEMAONLY="""
prefix schema: <http://schema.org/> 
DELETE {
    ?s ?p ?o.
} WHERE {
    ?s ?p ?o.
    FILTER ( ! (strstarts(str(?p),"http://schema.org") || strstarts(str(?o),"http://schema.org")) )
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
    
    def compare(self):
        form = CompareSelectForm()
        dataToDisplay = False
        if form.source.data:
#            flash("Selection '%s'" % form.source.data)
#            flash("Source type '%s'" % form.sourceType.data)
#            flash("Source format '%s'" % form.sourceFormat.data)
#            flash("Display format '%s'" % form.outFormat.data)
            
            self.source = form.source.data
            self.sourceType = form.sourceType.data
            self.sourceFormat = form.sourceFormat.data
            self.outFormat = form.outFormat.data
        
            self.getSource() #Go get imput

            if len(self.graph): #We got some imput
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
        self.graph = rdflib.Graph()
        sformat = self.sourceFormat
        if sformat == 'auto':
            sformat = None
            ext = os.path.splitext(self.source)[1]
            if ext:
                sformat = ext[1:]
                
        if self.sourceType == 'url':
            try:
                if sformat:
                    self.graph.parse(source=self.source, format=sformat)
                else:
                    self.graph.parse(source=self.source)
            except Exception as e:
                print("RDF Parse error: %s" % e)
                flash("Error no identifiable rdf returned: %s" % e)
                
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
                flash("Error '%s' records returned from LoC" % count)
                return
            
            rdfnodes = doc.getElementsByTagNameNS("http://www.w3.org/1999/02/22-rdf-syntax-ns#","RDF")
            if not rdfnodes:
                flash("LoC Record load error: Cannot identify RDF:rdf node in respose")
                print("LoCSRUResponse - XML Load error: Cannot identify <rdf:RDF> node in response")
                return
            else:
                bf = rdfnodes[0].toxml()
        except Exception as e:
            print("LoCSRUResponse - XML Load error: %s" % e)
            flash("Error retreving LoC record: %s" % e)
            
        self.graph.parse(data=bf, format='xml')


        
    def process(self):
        global SPARQLSCRIPT
        sparql = URLCache.get(SPARQLSCRIPT)
        if sparql:
            sparql = self.tokenSubstitute(sparql)
            try:
                self.graph.bind('schema', 'http://schema.org/')
                self.graph.update(sparql)
                return True
            except Exception as e:
                flash("Sparql parse error: %s" % e)
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
        global TOKENFILE,TOKENS
    
        if not TOKENS:
            today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
            now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            TOKENS = {
                "TODAY": today,
                "NOW": now
            }

            data = None
            if TOKENFILE:
                try:
                    tf = URLCache.get(TOKENFILE)
                    if tf:
                        data = json.loads(tf)
                except Exception as e:
                    print("Token file load error: \n%s" % (e))

            if data:
                TOKENS.update(data)

        if TOKENS:
            for t, v in TOKENS.items():
                string = string.replace("[[%s]]" % t ,v)
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
                

class CompareSelectForm(FlaskForm):
    source = StringField('Source')
    submit = SubmitField('Search')
    sourceType = SelectField('Source Type', choices=[('url','URL'),('locbib','LoC Bib ID'),('loclccn','LoC LCCN')])
    sourceFormat = SelectField('Source Format', choices=[('auto','auto'),('xml','RDF/XML'),('jsonld','JSON-LD'),('turtle','Turtle')])
    outFormat = SelectField('Disply Format', choices=[('jsonld','JSON-LD'),('xml','RDF/XML'),('turtle','Turtle')])
    
import datetime
import urllib.request

class URLCache():
    items = {}
    
    @classmethod
    def get(cls,url):
        itm = cls.items.get(url,None)
        if not itm:
            try:
                req = urllib.request.Request(url)
                data = urllib.request.urlopen(req).read()
                data = data.decode('utf-8')
                itm = item(data)
                cls.items[url] = itm
            except Exception as e:
                print("URL read error url '%s': \n%s" % (url,e))
                return None
        return itm.data

    @classmethod
    def flush(cls):
        cls.items = {}

class item():
    def __init__(self,data):
        self.data = data
        self.time = datetime.datetime.now()

    