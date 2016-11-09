# -*- coding: utf-8 -*-

# == IMPORTS =============================================================#
import os
import logging
import re
import math
# Use pickle for saving
import pickle

#Libraries for Zip file processing
# Can we use czipfile for faster processing?
import zipfile 
import tarfile
#from zip_open import zopen
from io import BytesIO #Python 3.5

# Import Beautiful Soup for XML parsing
from bs4 import BeautifulSoup

import utils

from datetime import datetime

# Import models for a patent document
from models import corpus_models as m
# == IMPORTS END =========================================================#

#test_path= "/media/SAMSUNG/Patent_Downloads/2001"

class MyCorpus():
    """Creates a new corpus object that simplifies processing of patent archive"""
    def __init__(self, path="/media/SAMSUNG/Patent_Downloads"):
        logging.basicConfig(filename="processing_class.log", format='%(asctime)s %(message)s')
        self.exten = (".zip",".tar")
        self.path = path
        # Check here that path exists?
        #Set regular expression for valid patent publication files
        self.FILE_FORMAT_RE = re.compile(r".+US\d+[A,B].+-\d+\.\w+")
        #Set a list of upper level zip files in the path - we ought to save the filename independently of path and join
        # later so that we can have the data at different paths
        self.first_level_files = [os.path.join(subdir,f) for (subdir, dirs, files) in os.walk(self.path) for f in files if f.lower().endswith(self.exten)]
        #Initialise arrays for lower level files
        self.processed_fl_files = []
        self.archive_file_list = []
        
        #Set English stopwords - in other class?
        #self.stopwords = stopwords.words('english')

    def get_archive_list(self):
        """ Generate a list of lower level archive files. """
        try:
            # Look for pre-existing list in file directory
            self.archive_file_list = pickle.load(open(os.path.join(self.path, "archive_list.p"), "rb"))
            print("Loading pre-existing file list\n")
        except:
            # If not file exists generate list
            print("Getting archive file list\n")
            for filename in self.first_level_files:
                print(".", end=".")
                if filename.lower().endswith(".zip"):
                    try:
                        #Look to see if we have already processed
                        if filename not in self.processed_fl_files:
                            afl = [(filename, name) for name in zipfile.ZipFile(filename, "r").namelist() if name.lower().endswith(self.exten) and self.FILE_FORMAT_RE.match(name)]
                            self.archive_file_list += afl
                            self.processed_fl_files.append(filename)
                    except Exception:
                        #Log error
                        logging.exception("Exception opening file:" + str(filename))
                elif filename.lower().endswith(".tar"):
                    try:
                        #Look to see if we have already processed
                        if filename not in self.processed_fl_files:
                            #There is no namelist() function in TarFile
                            current_file = tarfile.TarFile(filename, "r")
                            names = current_file.getnames()
                            current_file.close()
                            afl = [(filename, name) for name in names if name.lower().endswith(self.exten) and self.FILE_FORMAT_RE.match(name)]
                            self.archive_file_list += afl
                            self.processed_fl_files.append(filename)
                    except Exception:
                        #Log error
                        logging.exception("Exception opening file:" + str(filename))
            #Save archive list in path as pickle
            pickle.dump( self.archive_file_list, open( os.path.join(self.path, "archive_list.p"), "wb" ) )
    
    def get_archive_names(self, filename):
        """ Return names of files within archive having filename. """
        try:
            if filename.lower().endswith(".zip"):
                with zipfile.ZipFile(filename, "r") as z:
                    names = z.namelist()
            elif filename.lower().endswith(".tar"):
                with tarfile.TarFile(filename, "r") as t:
                    names = t.getnames()           
        except Exception:
            logging.exception("Exception opening file:" + str(filename))
            names = []
        return names
    
    def read_archive_file(self, filename, name):
        """ Read file data for XML_path nested within name archive within filename archive. """
        # Get xml file path from name
        file_name_section = name.rsplit('/',1)[1].split('.')[0]
        XML_path = file_name_section + '/' + file_name_section + ".XML"
       
        try:
            # For zip files
            if filename.lower().endswith(".zip"):
                with zipfile.ZipFile(filename, 'r') as z:
                    with z.open(name, 'r') as z2:
                        z2_filedata = BytesIO(z2.read())
                        with zipfile.ZipFile(z2_filedata,'r') as nested_zip:
                            with nested_zip.open(XML_path, 'r') as xml_file:
                                filedata = xml_file.read()
            
            # For tar files
            elif filename.lower().endswith(".tar"):
                with tarfile.TarFile(filename, 'r') as z:
                    z2 = z.extractfile(name)
                    with zipfile.ZipFile(z2) as nested_zip:
                        with nested_zip.open(XML_path) as xml_file:
                            filedata = xml_file.read()
        except:
            logging.exception("Exception opening file:" + str(XML_path))
            filedata = None
        
        return filedata
    
    def correct_file(self, name):
        """ Checks whether nested file 'name' is of correct type."""
        if name.lower().endswith(self.exten) and self.FILE_FORMAT_RE.match(name):
            return True
        else:
            return False
    # Function below takes about 1.5s to return each patent document 
    # > 5 days to parse one year's collection
    def iter_xml(self):
        """ Generator for xml file in corpus. """
        for filename in self.first_level_files:
            names = self.get_archive_names(filename)
            for name in names:
                if self.correct_file(name):
                    filedata = self.read_archive_file(filename, name)     
                    if filedata:
                        yield XMLDoc(filedata)
    
    def iter_filter_xml(self, class_list):
        """ Generator to return xml that matches the classifications in 
        class_list. """
        for filename in self.first_level_files:
            names = self.get_archive_names(filename)
            for name in names:
                if self.correct_file(name):
                    filedata = self.read_archive_file(filename, name)     
                    if filedata:
                        soup_object = XMLDoc(filedata)
                        match = False
                        for c in soup_object.classifications():
                            if c.match(class_list):
                                match = True
                        if match:
                            yield soup_object
    
    def read_xml(self, a_file_index):
        """ Read XML from a particular zip file (second_level_zip_file)
        that is nested within a first zip file (first_level_zip_file) 
        param: int a_file_index - an index to a file within archive_file_list"""
        filename, name = self.archive_file_list[a_file_index]
        return self.read_archive_file(filename, name)

    def get_doc(self, a_file_index):
        """ Read XML and return an XMLDoc object. """
        if not self.archive_file_list:
            self.get_archive_list()
        return XMLDoc(self.read_xml(a_file_index))

    def save(self):
        """ Save corpus object as pickle. """
        filename = self.path.replace("/","_") + ".p"
        pickle.dump( self, open( "savedata/" + filename, "wb" ) )
        
    @classmethod
    def load(cls, filename):
        """ Load a corpus by filename. """
        return pickle.load(open(filename, "rb"))
        
    def indexes_by_classification(self, class_list):
        """ Get a list of indexes of publications that match the supplied 
        class list.
        param: list of Classification objects - class_list"""
        #If there is a pre-existing search save file, start from last recorded index
        try:
            with open(os.path.join(self.path, "-".join([c.as_string() for c in class_list]) + ".data"), "r") as f:
                last_index = int(f.readlines()[-1].split(',')[0])+1
        except:
            last_index = 0
            
        if not self.archive_file_list:
            self.get_archive_list()
        # Iterate through publications
        matching_indexes = []
        
        for i in range(last_index, len(self.archive_file_list)):
            
            try:
                classifications = self.get_doc(i).classifications()
                # Look for matches with class_list entries bearing in mind None = ignore
                match = False
                for c in classifications:
                    if c.match(class_list):
                        match = True
                if match:
                    print("Match: ",str(i))
                    matching_indexes.append(i)
                    with open(os.path.join(self.path, "-".join([c.as_string() for c in class_list]) + ".data"), "a") as f:
                        print(i, end=",\n", file=f)
            except:
                print("Error with: ", self.archive_file_list[i][1])
        
        pickle.dump( matching_indexes, open( os.path.join(self.path, "-".join([c.as_string() for c in class_list]) + ".p"), "wb" ) )
        return matching_indexes

    def get_filtered_docs(self):
        """ Generator to return XMLDocs for matching indexes. """
        pass

class XMLDoc():
    """ Object to wrap the XML for a US Patent Document. """
    
    def __init__(self, filedata):
        """ Initialise object using read file data from read_xml above. """
        try:
            self.soup = BeautifulSoup(filedata, "xml")
        except:
            print("Error could not read file")

    def description_text(self):
        """ Return extracted description text."""
        paras = self.soup.find_all(["p", "paragraph"])
        return "\n".join([p.text for p in paras])
        
    def paragraph_list(self):
        """ Get list of paragraphs and numbers. """
        paras = self.soup.find_all(["p", "paragraph"])
        return [{
            "text":p.text, 
            "number": int(p.attrs['id'].split('-')[1])
            } 
            for p in paras if p.attrs['id'].split('-')[0] != "A"]
    
    def claim_text(self):
        """ Return extracted claim text."""
        claims = self.soup.find_all(["claim"])
        return "\n".join([c.text for c in claims])
        
    def claim_list(self):
        """ Return list of claims. """
        
        def get_dependency(claim):
            """ Sub function to get a dependency of a claim. """
            try:
                dependency = int(claim.find("dependent-claim-reference").attrs['depends_on'].split('-')[1])
            except AttributeError:
                try:
                    dependency = int(claim.find("claim-ref").attrs['idref'].split('-')[1])
                except AttributeError:
                    dependency = 0
            return dependency
        
        claims = self.soup.find_all(["claim"])
        # Can use claim-ref idref="CLM-00001" tag to check dependency
        # or dependent-claim-reference depends_on="CLM-00011"
        # Can use claim id="CLM-00001" to check number 
        return [{
                'text':claim.text, 
                'number':int(claim.attrs['id'].split('-')[1]),
                'dependency': get_dependency(claim)
                } for claim in claims]
    
    def publication_details(self):
        """ Return US publication details. """
        try:
            pub_section = self.soup.find("document-id")
            pub_number = pub_section.find("doc-number").text
            pub_kind = pub_section.find("kind-code").text
            pub_date = datetime.strptime(
                pub_section.find("document-date").text,
                "%Y%m%d")
            return (pub_number, pub_kind, pub_date)
        except AttributeError:
            return None
    
    def title(self):
        """ Return title. """
        return self.soup.find(["invention-title", "title-of-invention"]).text
    
    def all_text(self):
        """ Return description and claim text. """
        desc = self.description_text()
        claims = self.claim_text()
        return "\n".join([desc, claims])
        
    def classifications(self):
        """ Return IPC classification(s). """
        # Need to adapt - up to 2001 uses string under tag 'ipc'
        #Post 2009
        class_list = [
            Classification(
                each_class.find("section").text, 
                each_class.find("class").text,
                each_class.find("subclass").text,
                each_class.find("main-group").text,
                each_class.find("subgroup").text)
        for each_class in self.soup.find_all("classifications-ipcr")]
        # Pre 2009
        if not class_list:
            # Use function from patentdata on text of ipc tag
            class_list = Classification.process_classification(self.soup.find("ipc").text)
        return class_list
        
    def to_patentdoc(self):
        """ Return a patent doc object. """
        paragraphs = [m.Paragraph(**p) for p in self.paragraph_list()]
        description = m.Description(paragraphs)
        claims = [m.Claim(**c) for c in self.claim_list()]
        claimset = m.Claimset(claims)
        return m.PatentDoc(description, claimset, title=self.title())

class Classification():
    """ Object to model IPC classification. """
    def __init__(self, section, first_class=None, subclass=None, maingroup=None, subgroup=None):
        """ Initialise object and save classification portions. """
        self.section = section
        self.first_class = first_class
        self.subclass = subclass
        self.maingroup = maingroup
        self.subgroup = subgroup
        
    def __repr__(self):
        """ Print string representation of object. """
        return "<Classification {0}{1}{2} {3}/{4}>".format(
            self.section, 
            self.first_class, 
            self.subclass, 
            self.maingroup,
            self.subgroup)

    def match(self, list_of_classes):
        """ Determines if current classification matches passed list of 
        classifications. None = ignore for match. """
        # Convert to list if single classification is passed
        list_of_classes = utils.check_list(list_of_classes)
        match = False
        for classification in list_of_classes:
            if self.section == classification.section:
                if self.first_class == classification.first_class or not classification.first_class or not self.first_class:
                    if self.subclass == classification.subclass or not classification.subclass or not self.subclass:
                        if self.maingroup == classification.maingroup or not classification.maingroup or not self.maingroup:
                            if self.subgroup == classification.subgroup or not classification.subgroup or not self.subgroup:
                                match = True
        return match

    def as_string(self):
        """ Return a string representation. """
        return "C_{0}{1}{2}_{3}_{4}".format(
            self.section, 
            self.first_class, 
            self.subclass, 
            self.maingroup,
            self.subgroup)
 
    @classmethod
    def process_classification(cls, class_string):
        """ Extract IPC classfication elements from a class_string."""
        ipc = r'[A-H][0-9][0-9][A-Z][0-9]{1,4}\/?[0-9]{1,6}' #last bit can occur 1-3 times then we have \d+\\?\d+ - need to finish this
        p = re.compile(ipc)
        classifications = [
            cls(
                match.group(0)[0], 
                match.group(0)[1:3],
                match.group(0)[3],
                match.group(0)[4:].split('/')[0],
                match.group(0)[4:].split('/')[1]
            )
            for match in p.finditer(class_string)]
        return classifications



