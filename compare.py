import os
from flask import Flask, render_template, flash
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField

import rdflib
import rdflib_jsonld
from rdflib.parser import Parser
from rdflib.serializer import Serializer

rdflib.plugin.register("jsonld", Parser, "rdflib_jsonld.parser", "JsonLDParser")
rdflib.plugin.register("jsonld", Serializer, "rdflib_jsonld.serializer", "JsonLDSerializer")


class Compare():
    source = None
    sourctType = None
    sourceFormat = None
    outFormat = None
    graph =rdflib.Graph()
    
    def compare(self):
        form = CompareSelectForm()
        if form.source.data:
            flash("Selection '%s'" % form.source.data)
            flash("Source type '%s'" % form.sourceType.data)
            flash("Source format '%s'" % form.sourceFormat.data)
            flash("Display format '%s'" % form.outFormat.data)
            
            self.source = form.source.data
            self.sourceType = form.sourceType.data
            self.sourceFormat = form.sourceFormat.data
            self.outFormat = form.outFormat.data
        
            self.getSource()
        
        return render_template('compare.html',
                                title='View Schema',
                                form=form)
    
    def getSource(self):
        g = rdflib.Graph()
        sformat = self.sourceFormat
        if sformat == 'auto':
            sformat = None
            ext = os.path.splitext(self.source)[1]
            if ext:
                sformat = ext[1:]
            
        if self.sourceType == 'url':
            g.parse(source=self.source, format=sformat)
            
            print(g.serialize(format = self.outFormat ,auto_compact=True).decode('utf-8'))
        
    
    
    
    
class CompareSelectForm(FlaskForm):
    source = StringField('Source')
    submit = SubmitField('Search')
    sourceType = SelectField('Source Type', choices=[('url','URL'),('locbib','LoC Bib ID'),('loclccn','LoC LCCN')])
    sourceFormat = SelectField('Source Format', choices=[('auto','auto'),('xml','RDF/XML'),('jsonld','JSON-LD'),('turtle','Turtle')])
    outFormat = SelectField('Disply Format', choices=[('jsonld','JSON-LD'),('xml','RDF/XML'),('turtle','Turtle')])
    