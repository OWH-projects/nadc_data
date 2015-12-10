import os
import csvkit
import fabric
from fabric.api import *
from fabric.operations import *
import collections
import pandas as pd
import datetime
from canonical.canonical import *
import time
import re
from twitter import *
import requests

fabric.state.output.status = False

def getConfig():
    """
    Cache list of config values.
    """
    
    with open("../config.txt", "rb") as w:
        c = w.readlines()
        c = [linebr.replace("\n", "") for linebr in c]
        return c

configlist = getConfig()
THISPATH = configlist[5]

def validDate(datestring):
    """
    Check for known bad dates, invalid dates, dates in the future
    """
    
    try:
        return GARBAGE_DATES[datestring]
    except:
        try:
            # is it a valid date?
            x = datetime.datetime.strptime(datestring, '%Y-%m-%d')
            # is the date before today?
            if x < datetime.datetime.now():
                return datestring
            else:
                return "broke"
        except:
            return "broke"


def getFloat(i):
    """
    Return a float or 0.0
    """
    
    if not i or i == "":
        return "0.0"
    else:
        return i


def lookItUp(input, param, namefield):
    """
    Check if a record exists in canonical donors lookup dict
    """
    
    try:
        return str(CANON[input][param])
    except:
        if param == "canonicalid":
            return input
        else:
            return namefield


def canonFlag(input):
    """
    Temporary workaround to display front-page canonical records
    """
    
    try:
        x = CANON[input]
        return "I"
    except:
        return ""


def canonOffice(rawstring, param):
    """
    Hit the office canonical dict to standardize office names
    """
    
    try:
        x = CANON_OFFICE[rawstring][param]
        return x
    except:
        return ""
        

def getDate():
    """
    Parse the "last updated" date from a file in the NADC data dump
    """
    
    q = open(THISPATH + "nadc_data/last_updated.py", "wb")
    with open(THISPATH + "nadc_data/DATE_UPDATED.TXT", "rb") as d:
        last_updated = d.readline().split(": ")[1].split(" ")[0].split("-")
        year = last_updated[0]
        month = last_updated[1].lstrip("0")
        day = last_updated[2].lstrip("0")
        q.write("import datetime\n\nLAST_UPDATED = datetime.date(" + year + ", " + month + ", " + day + ")")
    q.close()
        

def parseErrything():
    """
    Kicks out ready-to-upload data files:
        toupload/entity.txt
        toupload/candidate.txt
        toupload/donation.txt
        toupload/loan.txt
        toupload/expenditure.txt
        toupload/ballot.txt
    
    Forms we care about:
        A1: Most committees
        A1CAND: Candidates
        B1: Campaign statements for candidate or ballot question committees
        B1AB: Main donations table
        B1C: Loans to candidate or ballot question committees
        B1D: Expenditures by candidate or ballot question committees
        B2: Campaign statements for political party committees
        B2A: Contributions to candidate or ballot question committees
        B2B: Expenditures by party committees
        B4: Campaign statements for independent committees
        B4A: Donations to independent committees
        B4B1: Expenditures by independent committees
        B4B2: Federal and Out of State Disbursements
        B4B3: Administrative/Operating Disbursements
        B5: Late contributions
        B6: Reports of an independent expenditure or donation made by people or entities that are not registered as committees
        B6CONT: Contributions to committees by people who do not have an ID
        B6EXPEND: Expenditures made on behalf of committees by people who do not have an ID
        B7: Registration of corporations, unions and other associations
        B72: Direct contributions by corporations, unions and other associations
        B73: Indirect contributions by corporations, unions and other associations
        B9: Out of state expenditures/donations
        B9B: Out of state expenditures
        B11: Report of late independent expenditure    
        
    Assumptions:
        A "direct expenditure" or "cash disbursement" to a candidate or registered committee is equivalent to a donation and will be treated as such.
    """
    
    delim = "|"
    id_master_list = []
    rows_with_new_bad_dates = []
    
    entities = open(THISPATH + "nadc_data/toupload/entity-raw.txt", "wb")
    candidates = open(THISPATH + "nadc_data/toupload/candidate.txt", "wb")
    donations = open(THISPATH + "nadc_data/toupload/donations-raw.txt", "wb")
    loans = open(THISPATH + "nadc_data/toupload/loan.txt", "wb")
    expenditures = open(THISPATH + "nadc_data/toupload/expenditure.txt", "wb")
    
    #write headers to files that get deduped by pandas or whatever
    donations_headers = [
        "db_id",
        "cash",
        "inkind",
        "pledge",
        "inkind_desc",
        "donation_date",
        "donor_id",
        "recipient_id",
        "donation_year",
        "notes",
        "stance",
        "donor_name"
        ]
    donations.write("|".join(donations_headers) + "\n")
    
    entities_headers = [
        "nadcid",
        "name",
        "address",
        "city",
        "state",
        "zip",
        "entity_type",
        "notes",
        "employer",
        "occupation",
        "place_of_business",
        "dissolved_date",
        "date_we_care_about"
        ]
    entities.write("|".join(entities_headers) + "\n")
    
    print "\nPARSING RAW FILES"
    
    with open('forma1.txt', 'rb') as a1:
        """
        FormA1: Top-level table for committees. Supposed to include all committees in FormB1, FormB4, FormB2 reports, but we are going to be paranoid and not assume this is the case.
        
        Data is fed to Entity and Candidate tables. (We're treating ballot questions as candidates.)
        
        COLUMNS
        =======
        0: Committee ID Number
        1: Committee Name
        2: Committee Address
        3: Committee City
        4: Committee State
        5: Committee Zip
        6: Committee Type
        7: Date Received
        8: Postmark Date
        9: Nature Of Filing
        10: Ballot Question
        11: Oppose Ballot Question
        12: Ballot Type
        13: Date over Theshold
        14: Acronym
        15: Separate Seg Political Fund ID
        16: Separate Segregated Political Fund Name
        17: SSPF Address
        18: SSPF City
        19: SSPF State
        20: SSPF Zip
        21: SSPF Type
        22: Date Dissolved
        23: Date of Next Election
        24: Election Type
        25: Won General
        26: Won Primary
        """
        
        print "    forma1 ..."
        
        a1reader = csvkit.reader(a1, delimiter = delim)
        a1reader.next()
        
        for row in a1reader:
            a1_entity_id = row[0] #NADC ID
            if a1_entity_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(a1_entity_id)
                
                #Add to Entity
                a1_entity_name = ' '.join((row[1].upper().strip()).split()).replace('"',"") #Committee name
                a1_address = row[2] #Address
                a1_city = row[3] #City
                a1_state = row[4] #State
                a1_zip = row[5] #ZIP
                #a1_entity_type = row[6].strip().upper() #Committee type
                a1_entity_type = canonFlag(a1_entity_id) # canonical flag                
                a1_entity_dissolved = row[21] #Date dissolved
                a1_entity_date_of_thing_happening = row[7] #Date used to eval recency on dedupe
               
                """
                DB fields
                =========== 
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding a1_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                
                a1_entity_list = [
                    a1_entity_id,
                    a1_entity_name,
                    a1_address.upper(),
                    a1_city.upper(),
                    a1_state.upper(),
                    a1_zip,
                    a1_entity_type,
                    "",
                    "",
                    "",
                    "",
                    a1_entity_dissolved,
                    a1_entity_date_of_thing_happening,
                ]
                entities.write("|".join(a1_entity_list) + "\n")
                
                #is there a separate segregated political fund?
                if row[15] and row[15].strip() != "":
                    a1_sspf_id = row[15] #NADC ID
                    if a1_sspf_id not in GARBAGE_COMMITTEES:
                        #Append ID to master list
                        id_master_list.append(a1_sspf_id)
                        
                        #Add to Entity
                        a1_sspf_name = row[16] #Committee name
                        a1_sspf_address = row[17] #Address
                        a1_sspf_city = row[18] #City
                        a1_sspf_state = row[19] #State
                        a1_sspf_zip = row[20] #ZIP
                        #a1_sspf_type = row[21] #Committee type
                        a1_sspf_type = canonFlag(a1_sspf_id) # canonical flag
                        a1_sspf_entity_date_of_thing_happening = row[7] #Date used to eval recency on dedupe
                        
                        a1_sspf_list = [
                            a1_sspf_id,
                            a1_sspf_name,
                            a1_sspf_address,
                            a1_sspf_city,
                            a1_sspf_state,
                            a1_sspf_zip,
                            a1_sspf_type,
                            "",
                            "",
                            "",
                            "",
                            a1_sspf_entity_date_of_thing_happening,
                        ]
                        entities.write("|".join(a1_sspf_list) + "\n")
                    
                #is this a ballot question?
                if row[6].upper().strip() == "B":
                    a1_nadc_id = row[0]
                    if a1_nadc_id not in GARBAGE_COMMITTEES:
                        a1_entity_name = ' '.join((row[1].upper().strip()).split()).replace('"',"") #Committee name
                        a1_ballot = ' '.join((row[10].upper().strip()).split()).replace('"',"")
                        a1_ballot_type = row[12].upper().strip() #(I=Initiative, R=Recall, F=Referendum, C=Constitutional Amendment)
                        a1_ballot_stance = row[11].strip() #(0=Support, 1=Oppose)
                        
                        #Unpack lookup to replace known bad strings
                        for item in GARBAGE_STRINGS:
                            a1_entity_name = a1_entity_name.upper().strip().replace(*item)

                        ballot_types = {
                            "I": "Initiative",
                            "R": "Recall",
                            "F": "Referendum",
                            "C": "Constitutional Amendment",
                            "O": "Other"
                        }
                        
                        def ballotType(str):
                            try:
                                return ballot_types[str]
                            except:
                                return "Uncategorized"
                
                        """
                        DB fields
                        =========
                        cand_id, cand_name, committee_id, office_dist, office_govt, office_title, stance, donor_id, notes, db_id (""), govslug
                        """
                        a1_ballot_cand_list = [
                            "BQCAND" + a1_nadc_id,
                            a1_entity_name,
                            a1_nadc_id,
                            "",
                            "Ballot question",
                            ballotType(a1_ballot_type),
                            a1_ballot_stance,
                            "",
                            a1_ballot,
                            "",
                            ""
                        ]
                        candidates.write("|".join(a1_ballot_cand_list) + "\n")

    
    with open('forma1cand.txt', 'rb') as a1cand:
        """
        FormA1CAND: Candidates connected to committees

        Data is fed to Candidate table
        
        COLUMNS
        =======
        0: Form A1 ID Number
        1: Date Received
        2: Candidate ID
        3: Candidate Last Name
        4: Candidate First Name
        5: Candidate Middle Initial
        6: Support/Oppose
        7: Office Sought
        8: Office Title
        9: Office Description
        
        """
        
        print "    forma1cand ..."
        
        a1candreader = csvkit.reader(a1cand, delimiter = delim)
        a1candreader.next()

        for row in a1candreader:
            a1cand_id = row[2] #Candidate ID
            a1cand_committee_id = row[0] #Candidate Committee ID
            
            if a1cand_committee_id not in GARBAGE_COMMITTEES:
                id_master_list.append(a1cand_committee_id)
                
                #Add to Entity
                a1cand_entity_name = ""
                a1cand_address = ""
                a1cand_city = ""
                a1cand_state = ""
                a1cand_zip = ""
                #a1cand_entity_type = ""
                a1cand_entity_type = canonFlag(a1cand_committee_id) # canonical flag
                a1cand_entity_dissolved = ""
                a1cand_entity_date_of_thing_happening = row[1] #Date used to eval recency on dedupe
               
                """
                DB fields
                =========== 
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding a1cand_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                
                a1cand_entity_list = [
                    a1cand_committee_id,
                    a1cand_entity_name,
                    a1cand_address,
                    a1cand_city,
                    a1cand_state,
                    a1cand_zip,
                    a1cand_entity_type,
                    "",
                    "",
                    "",
                    "",
                    a1cand_entity_dissolved,
                    a1cand_entity_date_of_thing_happening,
                ]
                entities.write("|".join(a1cand_entity_list) + "\n")
            
            if a1cand_committee_id not in GARBAGE_COMMITTEES and a1cand_id not in GARBAGE_COMMITTEES:
                #Append to Candidate
                a1cand_cand_last = row[3] #Last name
                a1cand_cand_first = row[4] #First name
                a1cand_cand_mid = row[5] #Middle initial
                a1cand_cand_full_name = " ".join([a1cand_cand_first, a1cand_cand_mid, a1cand_cand_last]) #Full name
                a1cand_cand_full_name = " ".join((a1cand_cand_full_name.upper().strip()).split()).replace('"',"")
                a1cand_stance = row[6] #Does committee support or oppose candidate? 0 = support, 1 = oppose            
                a1cand_office_sought = " ".join((row[7].upper().strip()).split()).replace('"',"") #Office sought
                a1cand_office_title = " ".join((row[8].upper().strip()).split()).replace('"',"") #Office title
                a1cand_office_desc = " ".join((row[9].upper().strip()).split()).replace('"',"") #Office description
                
                a1cand_office_string = " ".join([a1cand_office_desc, a1cand_office_sought, a1cand_office_title])
                
                a1cand_office = canonOffice(a1cand_office_string, "office")
                a1cand_gov = canonOffice(a1cand_office_string, "gov")
                a1cand_dist = canonOffice(a1cand_office_string, "district")
                
                #Fixing a couple of weird edge cases
                for item in STANDARD_CANDIDATES:
                    a1cand_cand_full_name = a1cand_cand_full_name.upper().replace(*item).strip()
                    a1cand_id = a1cand_id.upper().replace(*item).strip()
        
                """
                DB fields
                =========
                cand_id, cand_name, committee_id, office_dist, office_govt, office_title, stance, donor_id, notes, db_id (""), govslug
                """
                a1cand_list = [
                    a1cand_id,
                    a1cand_cand_full_name,
                    a1cand_committee_id,
                    a1cand_dist,
                    a1cand_gov,
                    a1cand_office,
                    a1cand_stance,
                    "",
                    "",
                    "",
                    "",
                ]
                candidates.write("|".join(a1cand_list) + "\n")
    
    
    with open('formb1.txt', 'rb') as b1:
        """
        FormB1: Campaign statements for candidate or ballot question committees

        Data is added to Entity
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee Address
        2: Committee Type
        3: Committee City
        4: Committee State
        5: Committee Zip
        6: Committee ID Number
        7: Date Last Revised
        8: Last Revised By
        9: Date Received
        10: Postmark Date
        11: Microfilm Number
        12: Election Date
        13: Type of Filing
        14: Nature of Filing
        15: Additional Ballot Question
        16: Report Start Date
        17: Report End Date
        18: Field 1
        19: Field 2A
        20: Field 2B
        21: Field 2C
        22: Field 3
        23: Field 4A
        24: Field 4B
        25: Field 5
        26: Field 6
        27: Field 7A
        28: Field 7B
        29: Field 7C
        30: Field 7D
        31: Field 8A
        32: Field 8B
        33: Field 8C
        34: Field 8D
        35: Field 9
        36: Field 10
        37: Field 11
        38: Field 12
        39: Field 13
        40: Field 14
        41: Field 15
        42: Field 16
        43: Field 17
        44: Field 18
        45: Field 19
        46: Field 20
        47: Field 21
        48: Field 22
        49: Field 23
        50: Field 23
        51: Field 24
        52: Field 25
        53: Field 26
        54: Field 27
        55: Adjustment
        56: Total Unitemized Bills
        57: Total Unpaid Bills
        58: Total All Bills
        
        """
        
        print "    formb1 ..."
        
        b1reader = csvkit.reader(b1, delimiter = delim)
        b1reader.next()
        
        for row in b1reader:
            b1_entity_id = row[6]
            if b1_entity_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b1_entity_id)
                
                #Add to Entity
                b1_entity_name = ' '.join((row[0].upper().strip()).split()).replace('"',"") #Committee name
                b1_address = ' '.join((row[1].upper().strip()).split()).replace('"',"") #Address
                b1_city = ' '.join((row[3].upper().strip()).split()).replace('"',"") #City
                b1_state = ' '.join((row[4].upper().strip()).split()).replace('"',"") #State
                b1_zip = row[5].strip() #ZIP
                #b1_entity_type = row[2].strip().upper() #Committee type
                b1_entity_type = canonFlag(b1_entity_id) # canonical flag
                b1_entity_date_of_thing_happening = row[9] #Date used to eval recency on dedupe
                
                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b1_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                b1_entity_list = [
                    b1_entity_id,                    
                    b1_entity_name,
                    b1_address,
                    b1_city,
                    b1_state,
                    b1_zip,
                    b1_entity_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b1_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b1_entity_list) + "\n")

    
    with open('formb1ab.txt', 'rb') as b1ab:
        """
        FormB1AB: Main donations table

        Data is added to Entity and Donation tables
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee ID
        2: Date Received
        3: Type of Contributor
        4: Contributor ID
        5: Contribution Date
        6: Cash Contribution
        7: In-Kind Contribution
        8: Unpaid Pledges
        9: Contributor Last Name
        10: Contributor First Name
        11: Contributor Middle Initial
        12: Contributor Organization Name
        13: Contributor Address
        14: Contributor City
        15: Contributor State
        16: Contributor Zipcode
        """
        
        print "    formb1ab ..."
        
        b1abreader = csvkit.reader(b1ab, delimiter = delim)
        b1abreader.next()
        
        for row in b1abreader:
            b1ab_committee_id = row[1]
            b1ab_contributor_id = row[4]
            
            if b1ab_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b1ab_committee_id)
                
                #Add committee to Entity
                b1ab_committee_name = ' '.join((row[0].upper().strip()).split()).replace('"',"") #Committee name
                b1ab_committee_address = "" #Address
                b1ab_committee_city = "" #City
                b1ab_committee_state = "" #State
                b1ab_committee_zip = "" #ZIP
                #b1ab_committee_type = "" #Committee type
                b1ab_committee_type = canonFlag(b1ab_committee_id) # canonical flag
                b1ab_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe
                
                """
                DB fields
                ===========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b1ab_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                
                b1ab_committee_list = [
                    b1ab_committee_id,
                    b1ab_committee_name,
                    b1ab_committee_address,
                    b1ab_committee_city,
                    b1ab_committee_state,
                    b1ab_committee_zip,
                    b1ab_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b1ab_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b1ab_committee_list) + "\n")

            if b1ab_contributor_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b1ab_contributor_id)
                
                #Add contributor to Entity
                b1ab_contributor_last = row[9] #Contributor last name
                b1ab_contributor_first = row[10] #Contributor first name
                b1ab_contributor_mid = row[11] #Contributor middle name
                b1ab_contributor_org_name = row[12] #Contributor org name
                b1ab_concat_name = " ".join([b1ab_contributor_first, b1ab_contributor_mid, b1ab_contributor_last, b1ab_contributor_org_name])
                b1ab_contributor_name = ' '.join((b1ab_concat_name.upper().strip()).split()).replace('"',"") #Contributor name
                b1ab_contributor_address = row[13].upper().strip() #Address
                b1ab_contributor_city = row[14].upper().strip() #City
                b1ab_contributor_state = row[15].upper().strip() #State
                b1ab_contributor_zip = row[16] #ZIP
                #b1ab_contributor_type = row[3].upper().strip() #Contributor type
                b1ab_contributor_type = canonFlag(b1ab_contributor_id) # canonical flag
                b1ab_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe
                
                """
               DB fields
                =========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b1ab_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b1ab_contributor_list = [
                    b1ab_contributor_id,
                    b1ab_contributor_name,
                    b1ab_contributor_address,
                    b1ab_contributor_city,
                    b1ab_contributor_state,
                    b1ab_contributor_zip,
                    b1ab_contributor_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b1ab_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b1ab_contributor_list) + "\n")

            #Womp into donations
            if b1ab_contributor_id not in GARBAGE_COMMITTEES and b1ab_committee_id not in GARBAGE_COMMITTEES:
                #datetest
                b1ab_donation_date = row[5]
                b1ab_date_test = validDate(b1ab_donation_date)
                if b1ab_date_test == "broke":
                    b1ab_dict = {}
                    b1ab_dict["donor_id"] = row[10]
                    b1ab_dict["recipient_id"] = row[1]
                    b1ab_dict["lookup_name"] = ' '.join((row[0].upper().strip()).split()).replace('"',"")
                    b1ab_dict["source_table"] = "b1ab"
                    b1ab_dict["destination_table"] = "donation"
                    b1ab_dict["donation_date"] = b1ab_donation_date
                    rows_with_new_bad_dates.append(b1ab_dict)
                else:
                    b1ab_year = b1ab_date_test.split("-")[0]
                    if int(b1ab_year) >= 1999:
                        b1ab_cash = getFloat(str(row[6])) #cash                        
                        b1ab_inkind_amount = getFloat(str(row[7])) #inkind
                        b1ab_pledge_amount = getFloat(str(row[8])) #pledge
                        b1ab_inkind_desc = "" #in-kind description
                        
                        """
                        DB fields
                        =========
                        db_id, cash, inkind, pledge, inkind_desc, donation_date, donor_id, recipient_id, donation_year, notes, stance, donor_name
                        """
                        b1ab_donation_list = [                        
                            "",
                            b1ab_cash,
                            b1ab_inkind_amount,
                            b1ab_pledge_amount,
                            b1ab_inkind_desc,
                            b1ab_date_test,
                            b1ab_contributor_id,
                            b1ab_committee_id,
                            b1ab_year,
                            "",
                            "",
                            "",
                        ]
                        donations.write("|".join(b1ab_donation_list) + "\n")
    
    
    with open('formb1c.txt', 'rb') as b1c:
        """
        FormB1C: Loans to candidate or ballot question committees

        Data is added to Entity and Loan tables
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee ID
        2: Date Received
        3: Lender Name
        4: Lender Address
        5: Loan Date
        6: Amount Received
        7: Amount Repaid
        8: Amount Forgiven
        9: Paid by 3rd Party
        10: Guarantor
        """
        
        print "    formb1c ..."
        
        b1creader = csvkit.reader(b1c, delimiter = delim)
        b1creader.next()
        
        for row in b1creader:
            b1c_committee_id = row[1]
            if b1c_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b1c_committee_id)
                
                #Add committee to Entity
                b1c_committee_name = ' '.join((row[0].upper().strip()).split()).replace('"',"") #Committee name
                b1c_committee_address = "" #Address
                b1c_committee_city = "" #City
                b1c_committee_state = "" #State
                b1c_committee_zip = "" #ZIP
                #b1c_committee_type = "" #Committee type
                b1c_committee_type = canonFlag(b1c_committee_id) # canonical flag
                b1c_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe

                """
                DB fields
                =========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b1c_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                
                b1c_committee_list = [
                    b1c_committee_id,
                    b1c_committee_name,
                    b1c_committee_address,
                    b1c_committee_city,
                    b1c_committee_state,
                    b1c_committee_zip,
                    b1c_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b1c_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b1c_committee_list) + "\n")
                                
                #Womp loans into loan table
                b1c_lender_name = ' '.join((row[3].strip().upper()).split())
                b1c_lender_addr = row[4].upper().strip()
                b1c_loan_date = row[5]
                b1c_loan_amount = row[6]
                b1c_loan_repaid = row[7]
                b1c_loan_forgiven = row[8]
                b1c_paid_by_third_party = row[9]
                b1c_guarantor = row[10]
                b1c_loan_date_test = validDate(b1c_loan_date)
                if b1c_loan_date_test == "broke":
                    b1c_dict = {}
                    b1c_dict["donor_id"] = ""
                    b1c_dict["recipient_id"] = row[1]
                    b1c_dict["lookup_name"] = ' '.join((row[0].upper().strip()).split()).replace('"',"")
                    b1c_dict["source_table"] = "b1c"
                    b1c_dict["destination_table"] = "loans"
                    b1c_dict["donation_date"] = b1c_loan_date
                    rows_with_new_bad_dates.append(b1c_dict)
                else:
                    b1c_year = b1c_loan_date_test.split("-")[0]
                    if int(b1c_year) >= 1999:
                        
                        """
                        DB fields
                        ========
                        db_id, lender_name, lender_addr, loan_date, loan_amount, loan_repaid, loan_forgiven, paid_by_third_party, guarantor, committee_id, notes, stance, lending_committee_id
                        """
                        
                        b1c_loan_list = [
                            "", #DB ID
                            b1c_lender_name, #lender name
                            b1c_lender_addr, #lender address
                            b1c_loan_date_test, #loan date
                            b1c_loan_amount, #loan amount
                            b1c_loan_repaid, #amount repaid
                            b1c_loan_forgiven, #amount forgiven
                            b1c_paid_by_third_party, #amount covered by 3rd party
                            b1c_guarantor, #guarantor
                            b1c_committee_id, #committee ID
                            "", #notes field
                            "", #stance field
                            "", #lending committee ID
                        ]
                        loans.write("|".join(b1c_loan_list) + "\n")
    
    
    with open('formb1d.txt', 'rb') as b1d:
        """
        FormB1D: Expenditures by candidate or ballot question committees

        Data is added to Entity and Expenditure tables
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee ID
        2: Date Received
        3: Payee Name
        4: Payee Address
        5: Expenditure Purpose
        6: Expenditure Date
        7: Amount
        8: In-Kind
        """
        
        print "    formb1d ..."
        
        b1dreader = csvkit.reader(b1d, delimiter = delim)
        b1dreader.next()
    
        for row in b1dreader:
            b1d_committee_id = row[1]
            if b1d_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b1d_committee_id)
                
                #Add committee to Entity
                b1d_committee_name = ' '.join((row[0].upper().strip()).split()).replace('"',"") #Committee name
                b1d_committee_address = "" #Address
                b1d_committee_city = "" #City
                b1d_committee_state = "" #State
                b1d_committee_zip = "" #ZIP
                #b1d_committee_type = "" #Committee type
                b1d_committee_type = canonFlag(b1d_committee_id) # canonical flag
                b1d_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b1d_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                
                b1d_committee_list = [
                    b1d_committee_id,
                    b1d_committee_name,
                    b1d_committee_address,
                    b1d_committee_city,
                    b1d_committee_state,
                    b1d_committee_zip,
                    b1d_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b1d_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b1d_committee_list) + "\n")
                
                # womp expenditures in there
                b1d_exp_date = row[6]
                b1d_exp_date_test = validDate(b1d_exp_date)
                if b1d_exp_date_test == "broke":
                    b1d_dict = {}
                    b1d_dict["donor_id"] = ""
                    b1d_dict["recipient_id"] = row[1]
                    b1d_dict["lookup_name"] = ' '.join((row[0].upper().strip()).split()).replace('"',"")
                    b1d_dict["source_table"] = "b1d"
                    b1d_dict["destination_table"] = "expenditures"
                    b1d_dict["donation_date"] = b1d_exp_date
                    rows_with_new_bad_dates.append(b1d_dict)
                else:
                    b1d_year = b1d_exp_date_test.split("-")[0]
                    if int(b1d_year) >= 1999:
                        b1d_payee = ' '.join((row[3].upper().strip()).split()).replace('"',"")
                        b1d_address = ' '.join((row[4].upper().strip()).split()).replace('"',"")
                        b1d_exp_purpose = ' '.join((row[5].strip()).split()).replace('"',"")
                        b1d_amount = row[7]
                        b1d_inkind = row[8]
                        
                        """
                        DB fields
                        =========
                        db_id (""), payee (name, free text), payee_addr, exp_date, exp_purpose, amount, in_kind, committee_id (doing the expending), stance (support/oppose), notes, payee_committee_id (the payee ID, if exists), committee_exp_name (name of the committee doing the expending), raw_target (free text ID of target ID, will get shunted to candidate or committee ID on save), target_candidate_id, target_committee_id
                        """
                        b1d_exp_list = [
                            "",                        
                            b1d_payee,
                            b1d_address,
                            b1d_exp_date_test,
                            b1d_exp_purpose,
                            b1d_amount,
                            b1d_inkind,
                            b1d_committee_id,
                            "", #stance
                            "", #notes
                            "", #payee committee ID
                            b1d_committee_name, #name of committee doing the expending,
                            "", #raw target
                            "\N", #target candidate ID
                            "", #target committee ID                       
                        ]
                        expenditures.write("|".join(b1d_exp_list) + "\n")

    
    with open('formb2.txt', 'rb') as b2:
        """
        FormB2: Campaign statements for political party committees

        Data is added to Entity
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee Address
        2: Committee City
        3: Committee State
        4: Committee Zip
        5: Committee ID
        6: Date Received
        7: Date Last Revised
        8: Last Revised By
        9: Postmark Date
        10: Microfilm Number
        11: Election Date
        12: Type of Filing
        13: Nature Of Filing
        14: Report Start Date
        15: Report End Date
        16: Financial Activity
        17: Report ID
        """
        
        print "    formb2 ..."
        
        b2reader = csvkit.reader(b2, delimiter = delim)
        b2reader.next()
        
        for row in b2reader:
            b2_committee_id = row[5]
            if b2_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b2_committee_id)
                
                #Add committee to Entity
                b2_committee_name = ' '.join((row[0].upper().strip()).split()).replace('"',"") #Committee name
                b2_committee_address = ' '.join((row[1].upper().strip()).split()).replace('"',"") #Address
                b2_committee_city = ' '.join((row[2].upper().strip()).split()).replace('"',"") #City
                b2_committee_state = ' '.join((row[3].upper().strip()).split()).replace('"',"") #State
                b2_committee_zip = row[4] #ZIP
                #b2_committee_type = "" #Committee type
                b2_committee_type = canonFlag(b2_committee_id) # canonical flag
                b2_entity_date_of_thing_happening = row[6] #Date used to eval recency on dedupe

                """
                DB fields
                =========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b2_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b2_committee_list = [
                    b2_committee_id,
                    b2_committee_name,
                    b2_committee_address,
                    b2_committee_city,
                    b2_committee_state,
                    b2_committee_zip,
                    b2_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b2_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b2_committee_list) + "\n")
    
    
    with open('formb2a.txt', 'rb') as b2a:
        """
        FormB2A: Contributions to candidate or ballot question committees

        Data is added to Entity (probably uneccesarily) and Donation
        
        COLUMNS
        =======
        0: Committee ID
        1: Date Received
        2: Contributor ID
        3: Contribution Date
        4: Cash Contribution
        5: In-Kind Contribution
        6: Unpaid Pledges
        7: Contributor Name
        
        *** n.b. The column headings in the file include "Report ID", but it doesn't exist in the data ***
        """
        
        print "    formb2a ..."
        
        b2areader = csvkit.reader(b2a, delimiter = delim)
        b2areader.next()
        
        for row in b2areader:
            b2a_committee_id = row[0]
            b2a_contributor_id = row[2]
            
            if b2a_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b2a_committee_id)
                
                #Add committee to Entity
                b2a_committee_name = "" #Committee name
                b2a_committee_address = "" #Address
                b2a_committee_city = "" #City
                b2a_committee_state = "" #State
                b2a_committee_zip = "" #ZIP
                #b2a_committee_type = "" #Committee type
                b2a_committee_type = canonFlag(b2a_committee_id) # canonical flag
                b2a_entity_date_of_thing_happening = row[1] #Date used to eval recency on dedupe

                """
                DB fields
                =========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b2a_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b2a_committee_list = [
                    b2a_committee_id,
                    b2a_committee_name,
                    b2a_committee_address,
                    b2a_committee_city,
                    b2a_committee_state,
                    b2a_committee_zip,
                    b2a_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b2a_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b2a_committee_list) + "\n")
                
            if b2a_contributor_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b2a_contributor_id)
                
                #Add contributor to Entity
                b2a_contributor_name = ' '.join((row[7].upper().strip()).split()).replace('"',"") #Contributor name
                b2a_contributor_address = "" #Address
                b2a_contributor_city = "" #City
                b2a_contributor_state = "" #State
                b2a_contributor_zip = "" #ZIP
                #b2a_contributor_type = "" #Contributor type
                b2a_contributor_type = canonFlag(b2a_contributor_id) # canonical flag
                b2a_entity_date_of_thing_happening = row[1] #Date used to eval recency on dedupe

                """
                DB fields
                =========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b2a_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b2a_contributor_list = [
                    b2a_contributor_id,
                    b2a_contributor_name,
                    b2a_contributor_address,
                    b2a_contributor_city,
                    b2a_contributor_state,
                    b2a_contributor_zip,
                    b2a_contributor_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b2a_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b2a_contributor_list) + "\n")
    
    
    with open('formb2b.txt', 'rb') as b2b:
        """
        FormB2B: Expenditures by party committees on behalf of other committees

        Data is added to Entity, Donation and Expenditure
        
        We are treating a "direct expenditure" to a committee ("currency, check, money order, etc. given directly to the committee which the committee deposits into its bank account," per the NADC) as a donation
        
        COLUMNS
        =======
        0: Committee ID
        1: Date Received
        2: Committee ID Expenditure is For
        3: Support/Oppose
        4: Nature of Expenditure
        5: Expenditure Date
        6: Amount
        7: Description
        8: Line ID
        9: Committee Name Expenditure is For
        
        *** n.b. The column headings in the file include "Report ID", but it doesn't exist in the data ***
        """
        
        print "    formb2b ..."
        
        b2breader = csvkit.reader(b2b, delimiter = delim)
        b2breader.next()
        
        for row in b2breader:
            b2b_committee_id = row[0]
            b2b_target_id = row[2]
            
            if b2b_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b2b_committee_id)
                
                #Add committee to Entity
                b2b_committee_name = "" #Committee name
                b2b_committee_address = "" #Address
                b2b_committee_city = "" #City
                b2b_committee_state = "" #State
                b2b_committee_zip = "" #ZIP
                #b2b_committee_type = "" #Committee type
                b2b_committee_type = canonFlag(b2b_committee_id) # canonical flag
                b2b_entity_date_of_thing_happening = row[1] #Date used to eval recency on dedupe

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b2b_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b2b_committee_list = [
                    b2b_committee_id,
                    b2b_committee_name,
                    b2b_committee_address,
                    b2b_committee_city,
                    b2b_committee_state,
                    b2b_committee_zip,
                    b2b_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b2b_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b2b_committee_list) + "\n")
            
            if b2b_target_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b2b_target_id)
                
                #Add target to Entity
                b2b_target_name = ' '.join((row[9].upper().strip()).split()).replace('"',"") #target name
                b2b_target_address = "" #Address
                b2b_target_city = "" #City
                b2b_target_state = "" #State
                b2b_target_zip = "" #ZIP
                #b2b_target_type = "" #Committee type
                b2b_target_type = canonFlag(b2b_target_id) # canonical flag
                b2b_entity_date_of_thing_happening = row[1] #Date used to eval recency on dedupe

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b2b_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b2b_target_list = [
                    b2b_target_id,
                    b2b_target_name,
                    b2b_target_address,
                    b2b_target_city,
                    b2b_target_state,
                    b2b_target_zip,
                    b2b_target_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b2b_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b2b_target_list) + "\n")
    
            if b2b_committee_id not in GARBAGE_COMMITTEES and b2b_target_id not in GARBAGE_COMMITTEES:
                # womp expenditures into Donation or Expenditure
                b2b_exp_date = row[5]
                b2b_exp_date_test = validDate(b2b_exp_date)
                if b2b_exp_date_test == "broke":
                    b2b_dict = {}
                    b2b_dict["donor_id"] = row[0]
                    b2b_dict["recipient_id"] = row[2]
                    b2b_dict["lookup_name"] = ' '.join((row[9].upper().strip()).split()).replace('"',"")
                    b2b_dict["source_table"] = "b2b"
                    b2b_dict["destination_table"] = "expenditures"
                    b2b_dict["donation_date"] = b2b_exp_date
                    rows_with_new_bad_dates.append(b2b_dict)
                else:
                    b2b_year = b2b_exp_date_test.split("-")[0]
                    if int(b2b_year) >= 1999:
                        b2b_payee = ""
                        b2b_address = ""
                        b2b_purpose = ' '.join((row[7].strip()).split()).replace('"',"")
                        b2b_stance = row[3].strip().upper()
                        b2b_target_committee_id = row[2]
                        
                        #What type of expenditure was it? D=Direct, K=In-kind, I=Independent Expenditure
                        
                        #if direct expenditure, treat as donation
                        if row[4].upper().strip() == "D":
                            b2b_cash = getFloat(str(row[6])) #cash                        
                            b2b_inkind_amount = ""
                            b2b_pledge_amount = ""
                            b2b_inkind_desc = ""
                            
                            """
                            DB fields
                            =========
                            db_id, cash, inkind, pledge, inkind_desc, donation_date, donor_id, recipient_id, donation_year, notes, stance, donor_name
                            """
                            b2b_donation_list = [                        
                                "",
                                b2b_cash,
                                b2b_inkind_amount,
                                b2b_pledge_amount,
                                b2b_inkind_desc,
                                b2b_exp_date_test,
                                b2b_committee_id,
                                b2b_target_id,
                                b2b_year,
                                "",
                                b2b_stance,
                                "",
                            ]
                            donations.write("|".join(b2b_donation_list) + "\n")
                        
                        #else it's a true expenditure
                        else:
                            if row[4].upper().strip() == "K":
                                b2b_amount = ""
                                b2b_inkind = getFloat(str(row[6]))
                            else:
                                b2b_amount = getFloat(str(row[6]))
                                b2b_inkind = ""
                        
                        """
                        DB fields
                        =========
                        db_id (""), payee (name, free text), payee_addr, exp_date, exp_purpose, amount, in_kind, committee_id (doing the expending), stance (support/oppose), notes, payee_committee_id (the payee ID, if exists), committee_exp_name (name of the committee doing the expending), raw_target (free text ID of target ID, will get shunted to candidate or committee ID on save), target_candidate_id, target_committee_id
                        """
                        b2b_exp_list = [    
                            "",                        
                            b2b_payee,
                            b2b_address,
                            b2b_exp_date_test,
                            b2b_purpose,
                            b2b_amount,
                            b2b_inkind,
                            b2b_committee_id,
                            b2b_stance,
                            "", #notes
                            "", #payee committee
                            "", #name of committee doing the expending
                            b2b_target_committee_id, #raw target ID
                            "\N", #target candidate ID
                            "", #target committee ID                           
                        ]
                        expenditures.write("|".join(b2b_exp_list) + "\n")
            
            
    with open('formb4.txt', 'rb') as b4:
        """
        FormB4: Campaign statements for independent committees

        Data is added to Entity
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee Address
        2: Committee Type
        3: Committee City
        4: Committee State
        5: Committee Zip
        6: Committee ID
        7: Date Recevied
        8: Date Last Revised
        9: Last Revised By
        10: Postmark Date
        11: Microfilm Number
        12: Election Date
        13: Type of Filing
        14: Nature of Filing
        15: Report Start Date
        16: Report End Date
        17: Nature of Committee
        18: Field 1
        19: Field 2A
        20: Field 2B
        21: Field 2C
        22: Field 2D
        23: Field 3
        24: Field 4
        25: Field 5
        26: Field 6
        27: Field 7
        28: Field 8
        29: Field 9
        30: Field 10
        31: Field 11A
        32: Field 11B
        33: Field 11C
        34: Field 11D
        35: Field 12
        36: Field 13
        37: Field 14
        38: Field 15
        39: Field 16
        40: Field 17
        41: Field 18
        42: Field 19
        43: Field 20
        44: Field 21
        45: Field 22
        46: Field 23
        47: Field 24
        48: Field 25
        49: Field 26
        50: Description
        51: Report ID        
        """
        
        print "    formb4 ..."
        
        b4reader = csvkit.reader(b4, delimiter = delim)
        b4reader.next()
        
        for row in b4reader:
            b4_committee_id = row[6]
            if b4_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b4_committee_id)
                
                #Add committee to Entity
                b4_committee_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #Committee name
                b4_committee_address = ' '.join((row[1].strip().upper()).split()).replace('"',"") #Address
                b4_committee_city = ' '.join((row[3].strip().upper()).split()).replace('"',"") #City
                b4_committee_state = ' '.join((row[4].strip().upper()).split()).replace('"',"") #State
                b4_committee_zip = row[5] #ZIP
                #b4_committee_type = row[2].upper().strip() #Committee type (C=Candidate Committee, B=Ballot Question, P=Political Action Committee, T=Political Party Committee, I or R = Independent Reporting Committee, S=Separate Segregated Political Fund Committee)
                b4_committee_type = canonFlag(b4_committee_id) # canonical flag
                b4_entity_date_of_thing_happening = row[7] #Date used to eval recency on dedupe

                """
                DB fields
                ==========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b4_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b4_committee_list = [
                    b4_committee_id,
                    b4_committee_name,
                    b4_committee_address,
                    b4_committee_city,
                    b4_committee_state,
                    b4_committee_zip,
                    b4_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b4_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b4_committee_list) + "\n")
        
     
    with open('formb4a.txt', 'rb') as b4a:
        """
        FormB4A: Donations to independent committees

        Data is added to Entity, Donation
        
        COLUMNS
        =======
        0: Committee ID
        1: Date Received
        2: Contributor ID
        3: Contribution Date
        4: Cash Contribution
        5: In-Kind Contribution
        6: Unpaid Pledges
        7: Contributor Name
        
        *** n.b. The column headings in the file include "Report ID", but it doesn't exist in the data ***
        """
        
        print "    formb4a ..."
        
        b4areader = csvkit.reader(b4a, delimiter = delim)
        b4areader.next()
        
        for row in b4areader:
            b4a_committee_id = row[0]
            b4a_contributor_id = row[2]
            
            if b4a_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b4a_committee_id)
                
                #Add committee to Entity
                b4a_committee_name = "" #Committee name
                b4a_committee_address = "" #Address
                b4a_committee_city = "" #City
                b4a_committee_state = "" #State
                b4a_committee_zip = "" #ZIP
                #b4a_committee_type = "" # Committee type
                b4a_committee_type = canonFlag(b4a_committee_id) # canonical flag
                b4a_entity_date_of_thing_happening = row[1] #Date used to eval recency on dedupe

                """
                DB fields
                =========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b4a_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b4a_committee_list = [
                    b4a_committee_id,
                    b4a_committee_name,
                    b4a_committee_address,
                    b4a_committee_city,
                    b4a_committee_state,
                    b4a_committee_zip,
                    b4a_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b4a_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b4a_committee_list) + "\n")

            if b4a_contributor_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b4a_contributor_id)
                
                #Add contributor to Entity
                b4a_contributor_name = ' '.join((row[7].strip().upper()).split()).replace('"',"") #Contributor name
                b4a_contributor_address = "" #Address
                b4a_contributor_city = "" #City
                b4a_contributor_state = "" #State
                b4a_contributor_zip = "" #ZIP
                #b4a_contributor_type = "" #Contributor type
                b4a_contributor_type = canonFlag(b4a_contributor_id) # canonical flag
                b4a_entity_date_of_thing_happening = row[1] #Date used to eval recency on dedupe

                """
                DB fields
                =========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b4a_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b4a_contributor_list = [
                    b4a_contributor_id,
                    b4a_contributor_name,
                    b4a_contributor_address,
                    b4a_contributor_city,
                    b4a_contributor_state,
                    b4a_contributor_zip,
                    b4a_contributor_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b4a_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b4a_contributor_list) + "\n")
                
            #Womp into donations
            if b4a_contributor_id not in GARBAGE_COMMITTEES and b4a_committee_id not in GARBAGE_COMMITTEES:
                #datetest
                b4a_donation_date = row[3]
                b4a_date_test = validDate(b4a_donation_date)
                if b4a_date_test == "broke":
                    b4a_dict = {}
                    b4a_dict["donor_id"] = row[2]
                    b4a_dict["recipient_id"] = row[0]
                    b4a_dict["lookup_name"] = ' '.join((row[7].strip().upper()).split()).replace('"',"")
                    b4a_dict["source_table"] = "b4a"
                    b4a_dict["destination_table"] = "donation"
                    b4a_dict["donation_date"] = b4a_donation_date
                    rows_with_new_bad_dates.append(b4a_dict)
                else:
                    b4a_year = b4a_date_test.split("-")[0]
                    if int(b4a_year) >= 1999:
                        b4a_cash = getFloat(str(row[4])) #cash
                        b4a_inkind_amount = getFloat(str(row[5])) #inkind
                        b4a_pledge_amount = getFloat(str(row[6])) #pledge
                        b4a_inkind_desc = "" #in-kind description
                        
                        """
                        DB fields
                        =========
                        db_id, cash, inkind, pledge, inkind_desc, donation_date, donor_id, recipient_id, donation_year, notes, stance, donor_name
                        """
                        b4a_donation_list = [                        
                            "",
                            b4a_cash,
                            b4a_inkind_amount,
                            b4a_pledge_amount,
                            b4a_inkind_desc,
                            b4a_date_test,
                            b4a_contributor_id,
                            b4a_committee_id,
                            b4a_year,
                            "",
                            "",
                            "",
                        ]
                        donations.write("|".join(b4a_donation_list) + "\n")
      
      
    with open('formb4b1.txt', 'rb') as b4b1:
        """
        FormB4B1: Expenditures by independent committees

        Data is added to Entity, Expenditure, Donation, Loan
        
        We are treating a "direct expenditure" to a committee ("currency, check, money order, etc. given directly to the committee which the committee deposits into its bank account," per the NADC) as a donation
        
        COLUMNS
        =======
        0: Form ID Number
        1: Committee ID
        2: Date Received
        3: Committee Expenditure ID
        4: Support/Oppose
        5: Nature of Expenditure
        6: Expenditure Date
        7: Amount
        8: Expense Category
        9: Expenditure Committee Name
        
        *** n.b. The column headings in the file include "Report ID", but it doesn't exist in the data ***
        """
        
        print "    formb4b1 ..."
        
        b4b1reader = csvkit.reader(b4b1, delimiter = delim)
        b4b1reader.next()
        
        for row in b4b1reader:
            b4b1_committee_id = row[1]
            b4b1_target_id = row[3]
            
            if b4b1_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b4b1_committee_id)
                
                #Add committee to Entity
                b4b1_committee_name = "" #Committee name
                b4b1_committee_address = "" #Address
                b4b1_committee_city = "" #City
                b4b1_committee_state = "" #State
                b4b1_committee_zip = "" #ZIP
                #b4b1_committee_type = "" #Committee type
                b4b1_committee_type = canonFlag(b4b1_committee_id) # canonical flag
                b4b1_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business
                
                We're adding b4b1_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b4b1_committee_list = [
                    b4b1_committee_id,
                    b4b1_committee_name,
                    b4b1_committee_address,
                    b4b1_committee_city,
                    b4b1_committee_state,
                    b4b1_committee_zip,
                    b4b1_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b4b1_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b4b1_committee_list) + "\n")
                
            if b4b1_target_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b4b1_target_id)
                
                #Add target to Entity
                b4b1_target_name = ' '.join((row[9].strip().upper()).split()).replace('"',"") #target name
                b4b1_target_address = "" #Address
                b4b1_target_city = "" #City
                b4b1_target_state = "" #State
                b4b1_target_zip = "" #ZIP
                #b4b1_target_type = "" #target type
                b4b1_target_type = canonFlag(b4b1_target_id) # canonical flag
                b4b1_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business
                
                We're adding b4b1_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b4b1_target_list = [
                    b4b1_target_id,
                    b4b1_target_name,
                    b4b1_target_address,
                    b4b1_target_city,
                    b4b1_target_state,
                    b4b1_target_zip,
                    b4b1_target_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b4b1_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b4b1_target_list) + "\n")

            if b4b1_target_id not in GARBAGE_COMMITTEES and b4b1_committee_id not in GARBAGE_COMMITTEES:
                #datetest
                b4b1_transaction_date = row[6]
                b4b1_date_test = validDate(b4b1_transaction_date)
                if b4b1_date_test == "broke":
                    b4b1_dict = {}
                    b4b1_dict["donor_id"] = row[1]
                    b4b1_dict["recipient_id"] = row[3]
                    b4b1_dict["lookup_name"] = ' '.join((row[9].strip().upper()).split()).replace('"',"")
                    b4b1_dict["source_table"] = "b4b1"
                    b4b1_dict["destination_table"] = "expenditure_or_loan"
                    b4b1_dict["donation_date"] = b4b1_transaction_date
                    rows_with_new_bad_dates.append(b4b1_dict)
                else:
                    b4b1_year = b4b1_date_test.split("-")[0]
                    if int(b4b1_year) >= 1999:
                        b4b1_transaction_type = row[5].upper().strip()
                        #(D=Direct Expenditure, I=In-Kind Expenditure, L=Loan, E=Independent Expenditure)
                        
                        #Is it a loan?
                        if b4b1_transaction_type == "L":
                            b4b1_lender_name = ' '.join((row[9].strip().upper()).split()).replace('"',"") #lending committee name
                            b4b1_lender_addr = ""
                            b4b1_loan_amount = row[7]
                            b4b1_loan_repaid = 0.00
                            b4b1_loan_stance = row[4].strip() #0=Support, 1=Oppose
                            b4b1_loan_forgiven = 0.00
                            b4b1_paid_by_third_party = 0.00
                            b4b1_guarantor = ""
                            b4b1_committee_id = row[3] # committee receiving the loan
                            b4b1_lending_committee_id = b4b1_target_id #lending committee ID
                            
                            """
                            DB fields
                            =========
                            db_id, lender_name, lender_addr, loan_date, loan_amount, loan_repaid, loan_forgiven, paid_by_third_party, guarantor, committee_id, notes, stance, lending_committee_id
                            """
                            b4b1_loan_list = [
                                "", #DB ID
                                b4b1_lender_name, #lender name
                                b4b1_lender_addr, #lender address
                                b4b1_date_test, #loan date
                                str(getFloat(b4b1_loan_amount)), #loan amount
                                str(getFloat(b4b1_loan_repaid)), #amount repaid
                                str(getFloat(b4b1_loan_forgiven)), #amount forgiven
                                str(getFloat(b4b1_paid_by_third_party)), #amount covered by 3rd party
                                b4b1_guarantor, #guarantor
                                b4b1_committee_id, #committee ID
                                "", #notes field
                                b4b1_loan_stance, #stance field
                                b4b1_lending_committee_id, #lending committee ID
                            ]
                            loans.write("|".join(b4b1_loan_list) + "\n")
                        
                        
                        # Is it a direct expenditure, i.e. a donation?
                        elif b4b1_transaction_type == "D":
                            b4b1_cash = getFloat(str(row[7])) #cash                        
                            b4b1_inkind_amount = ""
                            b4b1_pledge_amount = ""
                            b4b1_inkind_desc = ""
                            b4b1_don_stance = row[4].strip() #0=Support, 1=Oppose
                            
                            """
                            DB fields
                            =========
                            db_id, cash, inkind, pledge, inkind_desc, donation_date, donor_id, recipient_id, donation_year, notes, stance, donor_name
                            """
                            b4b1_donation_list = [                        
                                "",
                                b4b1_cash,
                                b4b1_inkind_amount,
                                b4b1_pledge_amount,
                                b4b1_inkind_desc,
                                b4b1_date_test,
                                b4b1_committee_id,
                                b4b1_target_id,
                                b4b1_year,
                                "",
                                b4b1_don_stance,
                                "",
                            ]
                            donations.write("|".join(b4b1_donation_list) + "\n")
                        
                        #Or is it a true expenditure?
                        else:
                            b4b1_payee = ""
                            b4b1_address = ""
                            b4b1_exp_purpose = ""
                            b4b1_exp_stance = row[4].strip() #0=Support, 1=Oppose
                            b4b1_committee_id = row[1] #committee ID doing the expending
                            
                            #was it an in-kind expenditure?
                            if b4b1_transaction_type.strip().upper() == "I":
                                b4b1_exp_inkind = row[7]
                                b4b1_exp_amount = "0.00"
                            else:
                                b4b1_exp_inkind = "0.00"
                                b4b1_exp_amount = row[7]
                            
                            """
                            DB fields
                            ==========
                            db_id (""), payee (name, free text), payee_addr, exp_date, exp_purpose, amount, in_kind, committee_id (doing the expending), stance (support/oppose), notes, payee_committee_id (the payee ID, if exists), committee_exp_name (name of the committee doing the expending), raw_target (free text ID of target ID, will get shunted to candidate or committee ID on save), target_candidate_id, target_committee_id
                            """
                            b4b1_exp_list = [
                                "",
                                b4b1_payee,
                                b4b1_address,
                                b4b1_date_test,
                                b4b1_exp_purpose,
                                b4b1_exp_amount,
                                b4b1_exp_inkind,
                                b4b1_committee_id,
                                b4b1_exp_stance,
                                "", #notes
                                "", #payee committee ID
                                "", #name of committee doing the expending
                                b4b1_target_id, #raw target ID
                                "\N", #target candidate ID
                                "", #target committee ID
                            ]
                            expenditures.write("|".join(b4b1_exp_list) + "\n")
    
    
    with open('formb4b2.txt', 'rb') as b4b2:
        """
        FormB4B2: Federal and out-of-state disbursements by independent committees

        Data is added to Entity, Donation
        
        We are treating cash disbursements the same as donations.
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee ID
        2: Date Received
        3: State Code
        4: Total
        5: Expense Category
        
        *** n.b. The column headings in the file include "Report ID", but it doesn't exist in the data ***
        """
        
        print "    formb4b2 ..."
        
        b4b2reader = csvkit.reader(b4b2, delimiter = delim)
        b4b2reader.next()
        
        for row in b4b2reader:
            b4b2_committee_id = row[1]
            
            if b4b2_committee_id not in GARBAGE_COMMITTEES:
            #Append ID to master list
                id_master_list.append(b4b2_committee_id)
                
                #Add committee to Entity
                b4b2_committee_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #Committee name
                b4b2_committee_address = "" #Address
                b4b2_committee_city = "" #City
                b4b2_committee_state = "" #State
                b4b2_committee_zip = "" #ZIP
                #b4b2_committee_type = "" #Committee type
                b4b2_committee_type = canonFlag(b4b2_committee_id) # canonical flag
                b4b2_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe

                """
                DB fields
                ==========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b4b2_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                
                b4b2_committee_list = [
                    b4b2_committee_id,
                    b4b2_committee_name,
                    b4b2_committee_address,
                    b4b2_committee_city,
                    b4b2_committee_state,
                    b4b2_committee_zip,
                    b4b2_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b4b2_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b4b2_committee_list) + "\n")
                
                #date test
                b4b2_transaction_date = row[2]
                b4b2_date_test = validDate(b4b2_transaction_date)
                if b4b2_date_test == "broke":
                    b4b2_dict = {}
                    b4b2_dict["donor_id"] = row[1]
                    b4b2_dict["recipient_id"] = ""
                    b4b2_dict["lookup_name"] = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                    b4b2_dict["source_table"] = "b4b2"
                    b4b2_dict["destination_table"] = "donation"
                    b4b2_dict["donation_date"] = b4b2_transaction_date
                    rows_with_new_bad_dates.append(b4b2_dict)
                else:
                    b4b2_year = b4b2_date_test.split("-")[0]
                    if int(b4b2_year) >= 1999:
                        #Add to Donation
                        b4b2_cash = getFloat(str(row[4])) #cash                        
                        b4b2_inkind_amount = ""
                        b4b2_pledge_amount = ""
                        b4b2_inkind_desc = "" #in-kind description
                        b4b2_donor_name = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                        
                        """
                        DB fields
                        =========
                        db_id, cash, inkind, pledge, inkind_desc, donation_date, donor_id, recipient_id, donation_year, notes, stance, donor_name
                        """
                        b4b2_donation_list = [                        
                            "",
                            b4b2_cash,
                            b4b2_inkind_amount,
                            b4b2_pledge_amount,
                            b4b2_inkind_desc,
                            b4b2_date_test,
                            b4b2_committee_id,
                            "",
                            b4b2_year,
                            "",
                            "",
                            b4b2_donor_name,
                        ]
                        donations.write("|".join(b4b2_donation_list) + "\n")
                
                
    with open('formb4b3.txt', 'rb') as b4b3:
        """
        FormB4B3: Administrative expenditures by independent committees

        Data is added to Entity, Expenditure
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee ID
        2: Date Received
        3: Payee Name
        4: Payee Address
        5: Purpose Of Disbursement
        6: Date of Disbursement
        7: Amount
        8: Expense Category
        
        *** n.b. The column headings in the file include "Report ID", but it doesn't exist in the data ***
        """
        
        print "    formb4b3 ..."
        
        b4b3reader = csvkit.reader(b4b3, delimiter = delim)
        b4b3reader.next()
        
        for row in b4b3reader:
            b4b3_committee_id = row[1]
            
            if b4b3_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b4b3_committee_id)
                
                #Add committee to Entity
                b4b3_committee_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #Committee name
                b4b3_committee_address = "" #Address
                b4b3_committee_city = "" #City
                b4b3_committee_state = "" #State
                b4b3_committee_zip = "" #ZIP
                #b4b3_committee_type = "" #Committee type
                b4b3_committee_type = canonFlag(b4b3_committee_id) # canonical flag
                b4b2_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b4b3_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b4b3_committee_list = [
                    b4b3_committee_id,
                    b4b3_committee_name,
                    b4b3_committee_address,
                    b4b3_committee_city,
                    b4b3_committee_state,
                    b4b3_committee_zip,
                    b4b3_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b4b2_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b4b3_committee_list) + "\n")
        
                #date test
                b4b3_transaction_date = row[6]
                b4b3_date_test = validDate(b4b3_transaction_date)
                if b4b3_date_test == "broke":
                    b4b3_dict = {}
                    b4b3_dict["donor_id"] = row[1]
                    b4b3_dict["recipient_id"] = row[3]
                    b4b3_dict["lookup_name"] = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                    b4b3_dict["source_table"] = "b4b3"
                    b4b3_dict["destination_table"] = "expenditure"
                    b4b3_dict["donation_date"] = b4b3_transaction_date
                    rows_with_new_bad_dates.append(b4b3_dict)
                else:
                    b4b3_year = b4b3_date_test.split("-")[0]
                    if int(b4b3_year) >= 1999:
                        #Add to Expenditure
                        
                        #Committee Name|Committee ID|Date Received|Payee Name|Payee Address|Purpose Of Disbursement|Date of Disbursement|Amount|Expense Category|Report ID
                        b4b3_committee_name = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                        b4b3_payee = ' '.join((row[3].strip().upper()).split()).replace('"',"")
                        b4b3_address = ' '.join((row[4].strip().upper()).split()).replace('"',"")
                        b4b3_purpose = ' '.join((row[5].strip().upper()).split()).replace('"',"")
                        b4b3_amount = row[7]
                        b4b3_inkind = ""
                        
                        """
                        DB fields
                        =========
                        db_id (""), payee (name, free text), payee_addr, exp_date, exp_purpose, amount, in_kind, committee_id (doing the expending), stance (support/oppose), notes, payee_committee_id (the payee ID, if exists), committee_exp_name (name of the committee doing the expending), raw_target (free text ID of target ID, will get shunted to candidate or committee ID on save), target_candidate_id, target_committee_id
                        """
                        b4b3_exp_list = [    
                            "",                          
                            b4b3_payee,
                            b4b3_address,
                            b4b3_date_test,
                            b4b3_purpose,
                            b4b3_amount,
                            b4b3_inkind,
                            b4b3_committee_id,
                            "", #stance
                            "", #notes
                            "", #payee committee ID
                            b4b3_committee_name,
                            "", #raw target
                            "\N", #target candidate ID
                            "", #target committee ID
                        ]
                        expenditures.write("|".join(b4b3_exp_list) + "\n")
       
    
    with open('formb5.txt', 'rb') as b5:
        """
        FormB5: Late donations

        Data is added to Entity, Donation
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee ID
        2: Date Received
        3: Date Last Revised
        4: Last Revised By
        5: Postmark Date
        6: Microfilm Number
        7: Contributor ID
        8: Type of Contributor
        9: Nature of Contribution
        10: Date of Contribution
        11: Amount
        12: Occupation
        13: Employer
        14: Place of Business
        15: Contributor Name
        """
        
        print "    formb5 ..."
        
        b5reader = csvkit.reader(b5, delimiter = delim)
        b5reader.next()
        
        for row in b5reader:
            b5_committee_id = row[1]
            b5_contributor_id = row[7]
            
            if b5_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b5_committee_id)
                
                #Add committee to Entity
                b5_committee_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #Committee name
                b5_committee_address = "" #Address
                b5_committee_city = "" #City
                b5_committee_state = "" #State
                b5_committee_zip = "" #ZIP
                #b5_committee_type = "" #Committee type
                b5_committee_type = canonFlag(b5_committee_id) # canonical flag
                b5_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b5_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                
                b5_committee_list = [
                    b5_committee_id,
                    b5_committee_name,
                    b5_committee_address,
                    b5_committee_city,
                    b5_committee_state,
                    b5_committee_zip,
                    b5_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b5_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b5_committee_list) + "\n")
        
            if b5_contributor_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b5_contributor_id)
                
                #Add contributor to Entity
                b5_contributor_name = ' '.join((row[15].strip().upper()).split()).replace('"',"") #Contributor name
                b5_contributor_address = "" #Address
                b5_contributor_city = "" #City
                b5_contributor_state = "" #State
                b5_contributor_zip = "" #ZIP
                #b5_contributor_type = row[8].strip().upper() #Contributor type (B=Business, I=Individual, C=Corporation, M=Candidate committee, P=PAC, Q=Ballot Question Committee, R=Political Party Committee)
                b5_contributor_type = canonFlag(b5_contributor_id) # canonical flag
                b5_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe
                b5_contributor_occupation = row[12].strip()
                b5_contributor_employer = row[13].strip()
                b5_contributor_place_of_business = row[14].strip()

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b5_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b5_contributor_list = [
                    b5_contributor_id,
                    b5_contributor_name,
                    b5_contributor_address,
                    b5_contributor_city,
                    b5_contributor_state,
                    b5_contributor_zip,
                    b5_contributor_type,
                    "",
                    b5_contributor_employer,
                    b5_contributor_occupation,
                    b5_contributor_place_of_business,
                    "",
                    b5_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b5_contributor_list) + "\n")
       
    
    #now we do the b6 tables with some fly csvjoin ish
    
    """
    FormB6 + B6CONT + B6EXPEND: Expenditures on behalf of committees by people or entities who do not have an ID
 
    Data is added to Entity, Expenditure
    
    COLUMNS
    =======
    0: Committee Name
    1: Form ID Number
    2: Committee ID
    3: Postmark Date
    4: Date Received
    5: Microfilm Number
    6: Expenditure Name
    7: Expend Phone
    8: Expend Address
    9: Expend City
    10: Expend State
    11: Expend Zip
    12: Election Date
    13: Recipient Name
    14: Recipient Address
    15: Expenditure Date
    16: Amount
    17: Description
    18: Date Last Revised
    19: Last Revised By
    20: Committee Name
    21: Form B6 ID
    22: Date Received
    23: Form ID
    24: Expenditure Date
    25: Amount
    26: Description
    27: Recipient Name
    28: Recipient Address
    
    """
    
    print "    formb6expend ..."
    
    with hide('running', 'stdout', 'stderr'):
        stitched_b6exp = local('csvjoin -d "|" -c "Form ID Number,Form B6 ID" --right formb6.txt formb6expend.txt | csvformat -D "|" |  sed -e \'1d\'', capture=True)
        
        ls = []
        for dude in stitched_b6exp.split("\n"):
            ls.append(dude.split("|"))
        for row in ls:
            b6_committee_id = row[2]
            
            if b6_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b6_committee_id)
                #Add committee to Entity
                b6_committee_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #Committee name
                b6_committee_address = "" #Address
                b6_committee_city = "" #City
                b6_committee_state = "" #State
                b6_committee_zip = "" #ZIP
                #b6_committee_type = "" #Committee type
                b6_committee_type = canonFlag(b6_committee_id) # canonical flag
                b6_entity_date_of_thing_happening = row[24] #Date used to eval recency on dedupe
                
                b6_committee_list = [
                    b6_committee_id,
                    b6_committee_name,
                    b6_committee_address,
                    b6_committee_city,
                    b6_committee_state,
                    b6_committee_zip,
                    b6_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b6_entity_date_of_thing_happening,
                ]
                
                #Womp into Expenditure
                
                #douse this particular garb fire with a flood of IF statements
                if row[15] and row[15] != "":
                    b6_transaction_date = row[15]
                elif row[24] and row[24] != "":
                    b6_transaction_date = row[24]
                elif row[4] and row[4] != "":
                    b6_transaction_date = row[4]
                elif row[22] and row[22] != "":
                    b6_transaction_date = row[22]
                elif row[3] and row[3] != "":
                    b6_transaction_date = row[3]
                
                #date test
                b6_date_test = validDate(b6_transaction_date)
                if b6_date_test == "broke":
                    b6_dict = {}
                    b6_dict["donor_id"] = row[6]
                    b6_dict["recipient_id"] = row[2]
                    b6_dict["lookup_name"] = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                    b6_dict["source_table"] = "b6expend"
                    b6_dict["destination_table"] = "expenditure"
                    b6_dict["donation_date"] = b6_transaction_date
                    #rows_with_new_bad_dates.append(b6_dict)
                    print b6_dict
                else:
                    b6_year = b6_date_test.split("-")[0]
                    if int(b6_year) >= 1999:
                        b6_payee = ' '.join((row[27].strip().upper()).split()).replace('"',"")
                        b6_payee_addr = ' '.join((row[28].strip().upper()).split()).replace('"',"")
                        b6_purpose = ' '.join((row[26].strip().upper()).split()).replace('"',"")
                        b6_amount = row[25]
                        b6_inkind = ""
                        b6_target_id = row[2]
                        b6_stance = ""
                        b6_exp_name = ' '.join((row[6].strip().upper()).split()).replace('"',"")
                        b6_exp_addr = " ".join([row[8].strip().upper(), row[9].strip().upper(), row[10].strip().upper(), row[11].strip().upper()])
                        b6_exp_addr = ' '.join(b6_exp_addr.split()).replace('"',"")
                        
                        """
                        DB fields
                        ========
                        db_id (""), payee (name, free text), payee_addr, exp_date, exp_purpose, amount, in_kind, committee_id (doing the expending), stance (support/oppose), notes, payee_committee_id (the payee ID, if exists), committee_exp_name (name of the committee doing the expending), raw_target (free text ID of target ID, will get shunted to candidate or committee ID on save), target_candidate_id, target_committee_id

                        """

                        b6_exp_list = [      
                            "",                          
                            b6_payee,
                            b6_payee_addr,
                            b6_date_test,
                            b6_purpose,
                            b6_amount,
                            b6_inkind,
                            "", #committee doing the expending (doesn't exist, is the point)
                            "", #stance
                            b6_exp_addr, #notes
                            "", #payee ID
                            b6_exp_name, #name of person/entity doing the expending
                            b6_committee_id, #raw target -- expenditure is made on its behalf
                            "\N", #target candidate ID
                            "", #target committee ID                    
                        ]
                        expenditures.write("|".join(b6_exp_list) + "\n")
    
    
    with open('formb7.txt', 'rb') as b7:
        """
        FormB7: Registration of corporations, unions and other associations

        Data is added to Entity
        
        COLUMNS
        =======
        0: Committee Name
        1: Committee ID
        2: Date Last Revised
        3: Last Revised By
        4: Date Received
        5: Postmark Date
        6: Microfilm Number
        7: Type of Contributor
        8: PAC ID
        9: Description Of Services
        10: Report ID
        11: PAC Name
        """
        
        print "    formb7 ..."
        
        b7reader = csvkit.reader(b7, delimiter = delim)
        b7reader.next()
        
        for row in b7reader:
            b7_committee_id = row[1]
            b7_sspf_committee_id = row[8]
            
            if b7_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b7_committee_id)
                
                #Add committee to Entity
                b7_committee_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #Committee name
                b7_committee_address = "" #Address
                b7_committee_city = "" #City
                b7_committee_state = "" #State
                b7_committee_zip = "" #ZIP
                #b7_committee_type = row[7].upper().strip() #Committee type (C=Corporation, L=Labor Organization, I=Industry or Trade Association, P=Professional Association)
                b7_committee_type = canonFlag(b7_committee_id) # canonical flag
                b7_entity_date_of_thing_happening = row[4] #Date used to eval recency on dedupe

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b7_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b7_committee_list = [
                    b7_committee_id,
                    b7_committee_name,
                    b7_committee_address,
                    b7_committee_city,
                    b7_committee_state,
                    b7_committee_zip,
                    b7_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b7_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b7_committee_list) + "\n")
            
            if b7_sspf_committee_id.strip() and b7_sspf_committee_id.strip() != "" and b7_sspf_committee_id.strip() not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b7_sspf_committee_id.strip())
                
                #Add sspf committee to Entity
                b7_sspf_committee_name = ' '.join((row[10].strip().upper()).split()).replace('"',"") #Committee name
                b7_sspf_committee_address = "" #Address
                b7_sspf_committee_city = "" #City
                b7_sspf_committee_state = "" #State
                b7_sspf_committee_zip = "" #ZIP
                b7_sspf_committee_descrip = ' '.join((row[9].strip().upper()).split()).replace('"',"")  #description
                #b7_sspf_committee_type = row[7].upper().strip() #Committee type (C=Corporation, L=Labor Organization, I=Industry or Trade Association, P=Professional Association)
                b7_sspf_committee_type = canonFlag(b7_sspf_committee_id) # canonical flag
                b7_sspf_entity_date_of_thing_happening = row[4] #Date used to eval recency on dedupe

                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b7_sspf_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b7_sspf_committee_list = [
                    b7_sspf_committee_id,
                    b7_sspf_committee_name,
                    b7_sspf_committee_address,
                    b7_sspf_committee_city,
                    b7_sspf_committee_state,
                    b7_sspf_committee_zip,
                    b7_sspf_committee_type,
                    b7_sspf_committee_descrip,
                    "",
                    "",
                    "",
                    "",
                    b7_sspf_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b7_sspf_committee_list) + "\n")
                
    
    with open('formb72.txt', 'rb') as b72:
        """
        FormB72: Direct contributions by corporations, unions and other associations

        Data is added to Entity, Donation
        
        COLUMNS
        =======
        0: Contributor Name
        1: Contributor ID
        2: Date Received
        3: Committee ID
        4: Contribution Date
        5: Amount
        6: Microfilm Number
        7: Committee Name
        
        *** n.b. committee ID/name and contributor ID/name headers are swapped in the raw data , also there is no Report ID, contrary to headers ***
        """
        
        print "    formb72 ..."
        
        b72reader = csvkit.reader(b72, delimiter = delim)
        b72reader.next()
        
        for row in b72reader:
            b72_committee_id = row[3]
            b72_contributor_id = row[1]
            
            if b72_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b72_committee_id)
                
                #Add committee to Entity
                b72_committee_name = ' '.join((row[7].strip().upper()).split()).replace('"',"") #Committee name
                b72_committee_address = "" #Address
                b72_committee_city = "" #City
                b72_committee_state = "" #State
                b72_committee_zip = "" #ZIP
                #b72_committee_type = "" #Committee type (C=Corporation, L=Labor Organization, I=Industry or Trade Association, P=Professional Association)
                b72_committee_type = canonFlag(b72_committee_id) # canonical flag
                b72_entity_date_of_thing_happening = row[4] #Date used to eval recency on dedupe
                
                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b72_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                
                b72_committee_list = [
                    b72_committee_id,
                    b72_committee_name,
                    b72_committee_address,
                    b72_committee_city,
                    b72_committee_state,
                    b72_committee_zip,
                    b72_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b72_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b72_committee_list) + "\n")
            
            if b72_contributor_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b72_contributor_id)
                
                #Add contributor to Entity
                b72_contributor_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #contributor name
                b72_contributor_address = "" #Address
                b72_contributor_city = "" #City
                b72_contributor_state = "" #State
                b72_contributor_zip = "" #ZIP
                #b72_contributor_type = "" #contributor type (C=Corporation, L=Labor Organization, I=Industry or Trade Association, P=Professional Association)
                b72_contributor_type = canonFlag(b72_contributor_id) # canonical flag
                b72_entity_date_of_thing_happening = row[4] #Date used to eval recency on dedupe
                
                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b72_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                b72_contributor_list = [
                    b72_contributor_id,
                    b72_contributor_name,
                    b72_contributor_address,
                    b72_contributor_city,
                    b72_contributor_state,
                    b72_contributor_zip,
                    b72_contributor_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b72_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b72_contributor_list) + "\n")

            #womp into Donation                
            if b72_committee_id not in GARBAGE_COMMITTEES and b72_contributor_id not in GARBAGE_COMMITTEES:
                #datetest
                b72_donation_date = row[4]
                b72_date_test = validDate(b72_donation_date)
                if b72_date_test == "broke":
                    b72_dict = {}
                    b72_dict["donor_id"] = row[1]
                    b72_dict["recipient_id"] = row[3]
                    b72_dict["lookup_name"] = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                    b72_dict["source_table"] = "b72"
                    b72_dict["destination_table"] = "donation"
                    b72_dict["donation_date"] = b72_donation_date
                    rows_with_new_bad_dates.append(b72_dict)
                else:
                    b72_year = b72_date_test.split("-")[0]
                    if int(b72_year) >= 1999:
                        b72_cash = getFloat(str(row[5])) #cash                        
                        b72_inkind_amount = "" #inkind
                        b72_pledge_amount = "" #pledge
                        b72_inkind_desc = "" #in-kind description
                        
                        """
                        DB fields
                        ========
                        db_id, cash, inkind, pledge, inkind_desc, donation_date, donor_id, recipient_id, donation_year, notes, stance, donor_name
                        """
                        b72_donation_list = [                        
                            "",
                            b72_cash,
                            b72_inkind_amount,
                            b72_pledge_amount,
                            b72_inkind_desc,
                            b72_date_test,
                            b72_contributor_id,
                            b72_committee_id,
                            b72_year,
                            "",
                            "",
                            " ".join((row[0].strip().upper()).split()).replace('"',""),
                        ]
                        donations.write("|".join(b72_donation_list) + "\n")
    
    
    with open('formb73.txt', 'rb') as b73:
        """
        FormB73: Indirect contributions by corporations, unions and other associations

        Data is added to Entity, Expenditure
        
        COLUMNS
        =======
        0: Contributor Name
        1: Contributor ID
        2: Date Received
        3: Committee ID
        4: Contribution Date
        5: Amount
        6: Nature Of Contribution
        7: Support/Oppose
        8: Description
        9: Microfilm Number
        10: Committee Name
        
        *** n.b. committee ID/name and contributor ID/name headers are swapped in the raw data, also there is no Report ID, contrary to headers ***
        
        We are grouping "personal service" expenditures ("personnel provided to or for the benefit of a candidate or ballot question or political party committee when the person rendering such services is paid his or her regular salary or is otherwise compensated by such corporation, union or association," per the NADC) with "in-kind" expenditures.
        
        """
        
        print "    formb73 ..."
        
        b73reader = csvkit.reader(b73, delimiter = delim)
        b73reader.next()
        
        for row in b73reader:
            b73_committee_id = row[3]
            b73_contributor_id = row[1]
            
            if b73_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b73_committee_id)
                
                #Add committee to Entity
                b73_committee_name = ' '.join((row[10].strip().upper()).split()).replace('"',"") #Committee name
                b73_committee_address = "" #Address
                b73_committee_city = "" #City
                b73_committee_state = "" #State
                b73_committee_zip = "" #ZIP
                #b73_committee_type = "" #Committee type (C=Corporation, L=Labor Organization, I=Industry or Trade Association, P=Professional Association)
                b73_committee_type = canonFlag(b73_committee_id) # canonical flag
                b73_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe
                
                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b73_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b73_committee_list = [
                    b73_committee_id,
                    b73_committee_name,
                    b73_committee_address,
                    b73_committee_city,
                    b73_committee_state,
                    b73_committee_zip,
                    b73_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b73_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b73_committee_list) + "\n")
                
            if b73_contributor_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b73_contributor_id)
                
                #Add contributor to Entity
                b73_contributor_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #contributor name
                b73_contributor_address = "" #Address
                b73_contributor_city = "" #City
                b73_contributor_state = "" #State
                b73_contributor_zip = "" #ZIP
                #b73_contributor_type = "" #contributor type (C=Corporation, L=Labor Organization, I=Industry or Trade Association, P=Professional Association)
                b73_contributor_type = canonFlag(b73_contributor_id) # canonical flag
                b73_entity_date_of_thing_happening = row[2] #Date used to eval recency on dedupe
                 
                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b73_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b73_contributor_list = [
                    b73_contributor_id,
                    b73_contributor_name,
                    b73_contributor_address,
                    b73_contributor_city,
                    b73_contributor_state,
                    b73_contributor_zip,
                    b73_contributor_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b73_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b73_contributor_list) + "\n")
            
            if b73_committee_id not in GARBAGE_COMMITTEES and b73_contributor_id not in GARBAGE_COMMITTEES:
                #date test
                b73_exp_date = row[4]
                b73_exp_date_test = validDate(b73_exp_date)
                if b73_exp_date_test == "broke":
                    b73_dict = {}
                    b73_dict["donor_id"] = ""
                    b73_dict["recipient_id"] = row[3]
                    b73_dict["lookup_name"] = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                    b73_dict["source_table"] = "b73"
                    b73_dict["destination_table"] = "expenditures_or_donations"
                    b73_dict["donation_date"] = b73_exp_date
                    rows_with_new_bad_dates.append(b73_dict)
                else:
                    b73_year = b73_exp_date_test.split("-")[0]
                    if int(b73_year) >= 1999:
                        #womp into Expenditure
                        b73_contrib_type = row[6].upper().strip() #(I=In-Kind, P=Personal Service, E=Independent Expenditure)
                        b73_payee = ""
                        b73_address = ""
                        b73_stance = row[7] #0=support, 1=oppose
                        b73_purpose = ' '.join((row[8].strip().upper()).split()).replace('"',"")
                        b73_contrib_name = ' '.join((row[0].strip().upper()).split()).replace('"',"")

                        if b73_contrib_type == "E":
                            b73_amount = row[5]
                            b73_inkind = ""
                        else:
                            b73_amount = ""
                            b73_inkind = row[5]
                        
                        """
                        DB fields
                        ========
                        db_id (""), payee (name, free text), payee_addr, exp_date, exp_purpose, amount, in_kind, committee_id (doing the expending), stance (support/oppose), notes, payee_committee_id (the payee ID, if exists), committee_exp_name (name of the committee doing the expending), raw_target (free text ID of target ID, will get shunted to candidate or committee ID on save), target_candidate_id, target_committee_id
                        """
                        b73_exp_list = [     
                            "",                          
                            b73_payee,
                            b73_address,
                            b73_exp_date_test,
                            b73_purpose,
                            b73_amount,
                            b73_inkind,
                            b73_contributor_id, #ID of committee doing the expending
                            b73_stance,
                            "", # notes
                            "", #payee committee ID
                            b73_contrib_name, # name of committee doing the expending
                            b73_committee_id, #raw target committee ID
                            "\N", #target candidate ID
                            "", #target committee ID                    
                        ]
                        expenditures.write("|".join(b73_exp_list) + "\n")
    
    
    with open('formb9.txt', 'rb') as b9:
        """
        FormB9: Out of State Contribution/Expenditure Report

        Data is added to Entity
        
        COLUMNS
        =======
        0: Contributor Name
        1: Form ID
        2: Contributor ID
        3: Postmark Date
        4: Date Received
        5: Microfilm Number
        6: Contributor Type
        7: Date Last Revised
        8: Last Revised By
        9: Contributor Phone
        """
        
        print "    formb9 ..."
        
        b9reader = csvkit.reader(b9, delimiter = delim)
        b9reader.next()
         
        for row in b9reader:
            b9_committee_id = row[2]
            
            if b9_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b9_committee_id)
                #Add committee to Entity
                b9_committee_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #committee name
                b9_committee_address = "" #Address
                b9_committee_city = "" #City
                b9_committee_state = "" #State
                b9_committee_zip = "" #ZIP
                #b9_committee_type = row[6].upper().strip() #committee type (C=Corporation, L=Labor Organization, I=Industry or Trade Organization, P=Professional Association)
                b9_committee_type = canonFlag(b9_committee_id) # canonical flag
                b9_entity_date_of_thing_happening = row[4] #Date used to eval recency on dedupe
                
                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b9_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                
                b9_committee_list = [
                    b9_committee_id,
                    b9_committee_name,
                    b9_committee_address,
                    b9_committee_city,
                    b9_committee_state,
                    b9_committee_zip,
                    b9_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b9_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b9_committee_list) + "\n")
        
    
    #use csvjoin on b9b, yo
    
    """
    FormB9B: Out-of-state expenditures, donations, loans

    Data is added to Entity, Expenditure, Donation, Loan
    
    COLUMNS
    =======
    0: Contributor Name
    1: Form ID
    2: Contributor ID
    3: Postmark Date
    4: Date Received
    5: Microfilm Number
    6: Contributor Type
    7: Date Last Revised
    8: Last Revised By
    9: Contributor Phone
    10: Contributor Name
    11: Form B9 ID
    12: Form ID
    13: Recipient ID
    14: Support/Oppose
    15: Nature of Expenditure
    16: Expenditure Date
    17: Previous Total
    18: Amount
    19: Total
    20: Description
    21: Entry Date
    22: Recipient Name
    
    """
    
    print "    formb9b ..."
    
    with hide('running', 'stdout', 'stderr'):
        stitched_b9exp = local('csvjoin -d "|" -c "Form ID,Form B9 ID" --right formb9.txt formb9b.txt | csvformat -D "|" |  sed -e \'1d\'', capture=True)
        
        ls = []
        for dude in stitched_b9exp.split("\n"):
            ls.append(dude.split("|"))
        for row in ls:
            b9_exp_committee_id = row[2]
            b9_exp_recipient_id = row[13]
            
            if b9_exp_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b9_exp_committee_id)
                
                #Add committee to Entity
                b9_exp_committee_name = ' '.join((row[10].strip().upper()).split()).replace('"',"") #committee name
                b9_exp_committee_address = "" #Address
                b9_exp_committee_city = "" #City
                b9_exp_committee_state = "" #State
                b9_exp_committee_zip = "" #ZIP
                #b9_exp_committee_type = row[6].upper().strip() #committee type (C=Corporation, L=Labor Organization, I=Industry or Trade Organization, P=Professional Association)
                b9_exp_committee_type = canonFlag(b9_exp_committee_id) # canonical flag
                b9_exp_entity_date_of_thing_happening = row[4] #Date used to eval recency on dedupe
                
                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b9_exp_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                
                b9_exp_committee_list = [
                    b9_exp_committee_id,
                    b9_exp_committee_name,
                    b9_exp_committee_address,
                    b9_exp_committee_state,
                    b9_exp_committee_zip,
                    b9_exp_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b9_exp_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b9_exp_committee_list) + "\n")
                
            if b9_exp_recipient_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b9_exp_recipient_id)
                
                #Add recipient to Entity
                b9_exp_recipient_name = ' '.join((row[22].strip().upper()).split()).replace('"',"") #recipient name
                b9_exp_recipient_address = "" #Address
                b9_exp_recipient_city = "" #City
                b9_exp_recipient_state = "" #State
                b9_exp_recipient_zip = "" #ZIP
                #b9_exp_recipient_type = "" #committee type (C=Corporation, L=Labor Organization, I=Industry or Trade Organization, P=Professional Association)
                b9_exp_recipient_type = canonFlag(b9_exp_recipient_id) # canonical flag
                b9_exp_entity_date_of_thing_happening = row[4] #Date used to eval recency on dedupe
                
                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b9_exp_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                """
                
                b9_exp_recipient_list = [
                    b9_exp_recipient_id,
                    b9_exp_recipient_name,
                    b9_exp_recipient_address,
                    b9_exp_recipient_city,
                    b9_exp_recipient_state,
                    b9_exp_recipient_zip,
                    b9_exp_recipient_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b9_exp_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b9_exp_recipient_list) + "\n")
                
            if b9_exp_committee_id not in GARBAGE_COMMITTEES and b9_exp_recipient_id not in GARBAGE_COMMITTEES:
                #datecheck
                b9_exp_date = row[16]
                b9_exp_date_test = validDate(b9_exp_date)
                if b9_exp_date_test == "broke":
                    b9_dict = {}
                    b9_dict["donor_id"] = row[2]
                    b9_dict["recipient_id"] = row[13]
                    b9_dict["lookup_name"] = ' '.join((row[22].strip().upper()).split()).replace('"',"")
                    b9_dict["source_table"] = "b9b"
                    b9_dict["destination_table"] = "expenditures_loans_donations"
                    b9_dict["donation_date"] = b9_exp_date
                    rows_with_new_bad_dates.append(b9_dict)
                else:
                    b9_year = b9_exp_date_test.split("-")[0]
                    if int(b9_year) >= 1999:
                        #what kind is it?
                        b9_contrib_type = row[15].upper().strip() #(A=Direct Contribution, B=In-Kind Contribution, C=Loans, D=Independent Expenditure, E=Pledge)
                        
                        if b9_contrib_type == "L":
                            # do loan shiz here
                            b9_lender_name = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                            b9_lender_addr = ""
                            b9_loan_amount = row[18]
                            b9_loan_repaid = ""
                            b9_loan_forgiven = ""
                            b9_loan_paid_by_third_party = ""
                            b9_loan_guarantor = ""
                            b9_loan_committee_id = row[13]
                            b9_loan_stance = row[14].upper().strip() # (S=Support, O=Oppose)
                            if b9_loan_stance == "S":
                                b9_loan_stance = "0"
                            elif b9_loan_stance == "0":
                                b9_loan_stance = "1"
                            else:
                                b9_loan_stance = ""
                            b9_loan_lending_committee_id = row[2] #lending committee ID
                            
                            """
                            DB fields
                            ========
                            db_id, lender_name, lender_addr, loan_date, loan_amount, loan_repaid, loan_forgiven, paid_by_third_party, guarantor, committee_id, notes, stance, lending_committee_id
                            """
                            
                            b9_loan_list = [
                                "", #DB ID
                                b9_lender_name, #lender name
                                b9_lender_addr, #lender address
                                b9_exp_date_test, #loan date
                                b9_loan_amount, #loan amount
                                b9_loan_repaid, #amount repaid
                                b9_loan_forgiven, #amount forgiven
                                b9_paid_by_third_party, #amount covered by 3rd party
                                b9_guarantor, #guarantor
                                b9_committee_id, #committee ID
                                "", #notes field
                                b9_loan_stance, #stance field
                                b9_loan_lending_committee_id, #lending committee ID
                            ]
                            loans.write("|".join(b9_loan_list) + "\n")
                        
                        # is it an expenditure, then, or
                        elif b9_contrib_type =="D":
                            b9_exp_payee = ""
                            b9_exp_address = ""
                            b9_exp_purpose = ' '.join((row[20].strip()).split()).replace('"',"")
                            b9_exp_amount = row[18]
                            b9_exp_inkind = ""
                            b9_exp_contributor_id = row[2]
                            b9_exp_contributor_name = ' '.join((row[0].upper().strip()).split()).replace('"',"")
                            b9_exp_stance = row[14].strip().upper()
                            b9_exp_stance = row[14].upper().strip() # (S=Support, O=Oppose)
                            if b9_exp_stance == "S":
                                b9_exp_stance = "0"
                            elif b9_exp_stance == "0":
                                b9_exp_stance = "1"
                            else:
                                b9_exp_stance = ""
                            
                            """
                            DB fields
                            ========
                            db_id (""), payee (name, free text), payee_addr, exp_date, exp_purpose, amount, in_kind, committee_id (doing the expending), stance (support/oppose), notes, payee_committee_id (the payee ID, if exists), committee_exp_name (name of the committee doing the expending), raw_target (free text ID of target ID, will get shunted to candidate or committee ID on save), target_candidate_id, target_committee_id
                            """
                            
                            b9_exp_list = [   
                                "",                              
                                b9_exp_payee,
                                b9_exp_address,
                                b9_exp_date_test,
                                b9_exp_purpose,
                                b9_exp_amount,
                                b9_exp_inkind,
                                b9_exp_contributor_id, #committee ID doing the expending
                                b9_exp_stance,
                                "", #notes
                                "", #payee ID
                                b9_exp_contributor_name, #name of committee doing the expending
                                b9_exp_recipient_id, #raw target committee ID
                                "\N", #target candidate ID
                                "", #target committee ID                           
                            ]
                            expenditures.write("|".join(b9_exp_list) + "\n")
                        
                        #else it's a donation
                        else:
                            b9_don_contributor_id = row[2]
                            b9_don_receiving_id = row[13]
                            b9_don_contributor_name = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                            b9_don_stance = row[14].upper().strip() # (S=Support, O=Oppose)
                            if b9_don_stance == "S":
                                b9_don_stance = "0"
                            elif b9_don_stance == "0":
                                b9_don_stance = "1"
                            else:
                                b9_don_stance = ""
                            
                            #is it a direct contribution?
                            if b9_contrib_type =="A":
                                b9_don_cash = getFloat(str(row[18]))
                                b9_don_inkind_amount = ""
                                b9_don_pledge_amount = ""
                                b9_don_inkind_desc = ""
                                
                            #is it an in-kind contribution?
                            elif b9_contrib_type == "B":
                                b9_don_inkind_amount = getFloat(str(row[18]))
                                b9_don_cash = ""
                                b9_don_pledge_amount = ""
                                b9_don_inkind_desc = ' '.join((row[20].upper().strip()).split()).replace('"',"")
                                
                            #is it a pledge?
                            elif b9_contrib_type == "E":
                                b9_don_pledge_amount = getFloat(str(row[18]))
                                b9_don_cash = ""
                                b9_don_inkind_amount = ""
                                b9_don_inkind_desc = ""
                            
                            """
                            DB fields
                            ========
                            DB id, cash, inkind, pledge, inkind_desc, donation_date, donor_id, recipient_id, donation_year, notes, stance, donor_name
                            """
                            b9_donation_list = [                        
                                "",
                                b9_don_cash,
                                b9_don_inkind_amount,
                                b9_don_pledge_amount,
                                b9_don_inkind_desc,
                                b9_exp_date_test,
                                b9_don_contributor_id,
                                b9_don_receiving_id,
                                b9_year,
                                "",
                                b9_don_stance,
                                b9_don_contributor_name,
                            ]
                            donations.write("|".join(b9_donation_list) + "\n")

    
    with open('formb11.txt', 'rb') as b11:
        """
        FormB11: Report of Late Independent Expenditure

        Data is added to Entity, Expenditure
        
        COLUMNS
        =======
        0: Committee Name
        1: Form ID
        2: Committee ID
        3: Postmark Date
        4: Date Received
        5: Microfilm Number
        6: Recipient Name
        7: Recipient Address
        8: Recipient City
        9: Recipient State
        10: Recipient Zip
        11: Recipient Phone
        12: Expenditure Date
        13: Amount
        14: Candidate ID
        15: Candidate Support/Oppose
        16: Ballot Question ID
        17: Ballot Support/Oppose
        18: Date Last Revised
        19: Last Revised By
        20: Candidate/Ballot Name
        """
        
        print "    formb11 ..."
        
        b11reader = csvkit.reader(b11, delimiter = delim)
        b11reader.next()
        
        for row in b11reader:
            b11_committee_id = row[2]
            b11_candidate_id = row[14]
            b11_ballot_id = row[16]
            
            if b11_committee_id not in GARBAGE_COMMITTEES:
                #Append ID to master list
                id_master_list.append(b11_committee_id)
                
                #Add committee to Entity
                b11_committee_name = ' '.join((row[0].strip().upper()).split()).replace('"',"") #committee name
                b11_committee_address = "" #Address
                b11_committee_city = "" #City
                b11_committee_state = "" #State
                b11_committee_zip = "" #ZIP
                #b11_committee_type = ""
                b11_committee_type = canonFlag(b11_committee_id) # canonical flag
                b11_entity_date_of_thing_happening = row[4] #Date used to eval recency on dedupe
                
                """
                DB fields
                ========
                nadcid, name, address, city, state, zip, entity_type, notes, employer, occupation, place_of_business, dissolved_date
                
                We're adding b11_entity_date_of_thing_happening so that later we can eval for recency on dedupe.
                
                """
                b11_committee_list = [
                    b11_committee_id,
                    b11_committee_name,
                    b11_committee_address,
                    b11_committee_city,
                    b11_committee_state,
                    b11_committee_zip,
                    b11_committee_type,
                    "",
                    "",
                    "",
                    "",
                    "",
                    b11_entity_date_of_thing_happening,
                ]
                entities.write("|".join(b11_committee_list) + "\n")
                
                # womp expenditures in there
                b11_exp_date = row[12]
                b11_exp_date_test = validDate(b11_exp_date)
                if b11_exp_date_test == "broke":
                    b11_exp_dict = {}
                    b11_exp_dict["donor_id"] = row[2]
                    b11_exp_dict["recipient_id"] = ' '.join((row[6].upper().strip()).split()).replace('"',"")
                    b11_exp_dict["lookup_name"] = ' '.join((row[0].strip().upper()).split()).replace('"',"")
                    b11_exp_dict["source_table"] = "b11"
                    b11_exp_dict["destination_table"] = "expenditures"
                    b11_exp_dict["donation_date"] = b11_exp_date
                    rows_with_new_bad_dates.append(b11_exp_dict)
                else:
                    b11_exp_year = b11_exp_date_test.split("-")[0]
                    if int(b11_exp_year) >= 1999:
                        b11_exp_payee = ' '.join((row[6].upper().strip()).split()).replace('"',"")
                        b11_exp_committee_name =  ' '.join((row[0].upper().strip()).split()).replace('"',"")
                        b11_exp_address = " ".join([row[7], row[8], row[9], row[10]])
                        b11_exp_address = ' '.join((b11_exp_address.upper().strip()).split()).replace('"',"")
                        b11_exp_purpose = ""
                        b11_exp_amount = row[13]
                        b11_exp_inkind = ""
                        b11_exp_target_name = row[20]
                        
                        if row[14] and row[14] != "" and row[15] and row[15] != "":
                            b11_exp_stance = row[15].upper().strip() # (S=Support, O=Oppose)
                            if b11_exp_stance == "S":
                                b11_exp_stance = "0"
                            elif b11_exp_stance == "0":
                                b11_exp_stance = "1"
                            else:
                                b11_exp_stance = ""
                            b11_exp_target_id = row[14]
                        else:
                            b11_exp_stance = row[17].upper().strip() # (S=Support, O=Oppose)
                            if b11_exp_stance == "S":
                                b11_exp_stance = "0"
                            elif b11_exp_stance == "0":
                                b11_exp_stance = "1"
                            else:
                                b11_exp_stance = ""
                            b11_exp_target_id = row[16]
                        
                        """
                        DB fields
                        =========
                        db_id (""), payee (name, free text), payee_addr, exp_date, exp_purpose, amount, in_kind, committee_id (doing the expending), stance (support/oppose), notes, payee_committee_id (the payee ID, if exists), committee_exp_name (name of the committee doing the expending), raw_target (free text ID of target ID, will get shunted to candidate or committee ID on save), target_candidate_id, target_committee_id
                        """
                        b11_exp_list = [  
                            "",                        
                            b11_exp_payee,
                            b11_exp_address,
                            b11_exp_date_test,
                            b11_exp_purpose,
                            b11_exp_amount,
                            b11_exp_inkind,
                            b11_committee_id, #ID of committee doing the expending
                            b11_exp_stance,
                            "", #notes
                            "", #payee ID
                            b11_exp_committee_name, #name of committee doing the expending
                            b11_exp_target_id, #raw target committee ID
                            "\N", #target candidate ID
                            "", #target committee ID                      
                        ]
                        expenditures.write("|".join(b11_exp_list) + "\n")
                
            
    entities.close()
    candidates.close()
    donations.close()
    loans.close()
    expenditures.close()
    
    #check for new bad dates
    if len(rows_with_new_bad_dates) > 0:
        if len(rows_with_new_bad_dates) == 1:
            s = "1 record with a bad date"
        else:
            s = str(len(rows_with_new_bad_dates)) + " records with bad dates"
        print "\n\nFound " + s + ". Go fix in canonical.py:"
        for thing in rows_with_new_bad_dates:
            print thing
        #local("killall parser.sh", capture=False)

    
    """
    Dedupe entity file
    =========
    - csvsort entity-raw.txt by date_we_care_about
    - loop over unique entity IDs (having taken the set of id_master_list)
    - grep for each ID in the sorted entity file (~1 million times faster than python)
    - loop over the results, compiling a dict with the most recent, non-empty values, if available
    - in the process, kill out variants of "(DISSOLVED)"
    - punch that record into a list
    - write that list to file
    """
    
    print "\n\nPREPPING ENTITY FILE"
    
    #get list of unique entity IDs
    uniques = list(set(id_master_list))
        
    print "   pre-duping ..."
    
    #dedupe sorted file
    clean_entity = pd.read_csv(THISPATH + "nadc_data/toupload/entity-raw.txt", delimiter="|", dtype={
        "nadcid": object,
        "name": object,
        "address": object,
        "city": object,
        "state": object,
        "zip": object,
        "entity_type": object,
        "notes": object,
        "employer": object,
        "occupation": object,
        "place_of_business": object,
        "dissolved_date": object,
        "date_we_care_about": object,
        }
    )
    
    deduped_entities = clean_entity.drop_duplicates(subset=["nadcid", "name", "address", "city", "state", "zip", "entity_type", "notes", "employer", "occupation", "place_of_business", "dissolved_date"])
    
    deduped_entities.to_csv(THISPATH + 'nadc_data/toupload/entities_deduped.txt', sep="|")
    
    print "   sorting ..."
    
    #sort input file by date
    with hide('running', 'stdout', 'stderr'):
        local('csvsort -d "|" -c 14 ' + THISPATH + 'nadc_data/toupload/entities_deduped.txt | csvformat -D "|" | sed -e \'1d\' > ' + THISPATH + 'nadc_data/toupload/entities_sorted_and_deduped.txt', capture=False)
    
    #get most current, complete data
    print "   grepping pre-duped, sorted file and deduping for recency and completeness ..."
    
    entity_final = open(THISPATH + "nadc_data/toupload/entity.txt", "wb")
    
    for idx, i in enumerate(uniques):
        #print str(idx)
        with hide('running', 'stdout', 'stderr'):
            grepstring = local('grep "' + i + '" ' + THISPATH + 'nadc_data/toupload/entities_sorted_and_deduped.txt', capture=True)
            g = grepstring.split("\n") #list of records that match
            interimdict = {}
            
            #set default values
            interimdict['id'] = ""
            interimdict['canonical_id'] = ""
            interimdict['name'] = ""
            interimdict['canon_name'] = ""
            interimdict['address'] = ""
            interimdict['city'] = ""
            interimdict['state'] = ""
            interimdict['zip'] = ""
            interimdict['entity_type'] = ""
            interimdict['employer'] = ""
            interimdict['occupation'] = ""
            interimdict['place_of_business'] = ""
            interimdict['dissolved_date'] = ""
            
            for dude in g:
                row = dude.split("|") #actual record
                
                nadcid = row[1]
                name = row[2]
                canonical_id = lookItUp(nadcid, "canonicalid", name)
                canonical_name = lookItUp(nadcid, "canonicalname", name)
                
                interimdict['id'] = nadcid
                interimdict['canonical_id'] = canonical_id
                
                #Unpack lookup to replace known bad strings
                for item in GARBAGE_STRINGS:
                    name = name.upper().replace(*item).strip()
                    canonical_name = canonical_name.upper().replace(*item).strip()
                
                #check for complete names
                if len(name) > 1:
                    interimdict['name'] = name
                if len(canonical_name) > 1:
                    interimdict['canon_name'] = canonical_name
                
                #check for complete address
                if len(row[3]) > 1 and len(row[4]) > 1 and len(row[5]) > 1 and len(row[6]) > 1:
                    interimdict['address'] = row[3]
                    interimdict['city'] = row[4]
                    interimdict['state'] = row[5]
                    interimdict['zip'] = row[6]

                #check for complete entity type
                if len(row[7]) >= 1:
                    interimdict['entity_type'] = row[7]

                #check for complete employer
                if len(row[9]) > 1:
                    interimdict['employer'] = row[9]
                    
                #check for complete occupation
                if len(row[10]) > 1:
                    interimdict['occupation'] = row[10]
                    
                #check for complete place of business
                if len(row[11]) > 1:
                    interimdict['place_of_business'] = row[11]
                
                #check for complete dissolved date
                if len(row[12]) > 1:
                    interimdict['dissolved_date'] = row[12]

            #append dict items to list
            outlist = [
                interimdict['id'],
                interimdict['canonical_id'],
                interimdict['name'],
                interimdict['canon_name'],
                interimdict['address'],
                interimdict['city'],
                interimdict['state'],
                interimdict['zip'],
                interimdict['entity_type'],
                "",
                interimdict['employer'],
                interimdict['occupation'],
                interimdict['place_of_business'],
                interimdict['dissolved_date']
            ]
            
            entity_final.write("|".join(outlist) + "\n")
    
    entity_final.close()
    
    
    """
    Dedupe donations file
    =========
    - call pandas drop_duplicates on a subset of fields
    - csvcut the columns we need out of this one
    - chop the header row and kill stray quotes
    """

    print "\n\nPREPPING DONATIONS FILE"
    print "    deduping ..."
    
    clean_donations = pd.read_csv(THISPATH + "nadc_data/toupload/donations-raw.txt", delimiter="|", dtype={
        "db_id": object,
        "cash": object,
        "inkind": object,
        "pledge": object,
        "inkind_desc": object,
        "donation_date": object,
        "donor_id": object,
        "recipient_id": object,
        "donation_year": object,
        "notes": object,
        "stance": object,
        "donor_name": object
        }
    )
    deduped_donations = clean_donations.drop_duplicates(subset=["donor_id", "donation_date", "recipient_id", "cash", "inkind", "pledge"])
    deduped_donations.to_csv(THISPATH + 'nadc_data/toupload/donations_almost_there.txt', sep="|")
    with hide('running', 'stdout', 'stderr'):
        local('csvcut -x -d "|" -c db_id,cash,inkind,pledge,inkind_desc,donation_date,donor_id,recipient_id,donation_year,notes,stance,donor_name ' + THISPATH + 'nadc_data/toupload/donations_almost_there.txt | csvformat -D "|" | sed -e \'1d\' -e \'s/\"//g\' > ' + THISPATH + 'nadc_data/toupload/donations.txt', capture=False)
    
    print "\n\nDONE."


    
@hosts('dataomaha.com')    
def goLive():
    """
    Upload last_updated.py to live server, load SQL dumps into Dataomaha database
    """
    
    env.user = configlist[2]
    env.password = configlist[3]
    
    with hide('running', 'stdout', 'stderr'):
        put(THISPATH + 'nadc_data/last_updated.py', configlist[6] + "nadc/")
        put(THISPATH + 'nadc_data/toupload/*.sql.gz', configlist[8] + "nadc/")
        run('cd ' + configlist[8] + 'nadc/ && for z in *.gz; do gunzip -f $z; done && for s in *.sql; do mysql -u ' + configlist[2] + ' -p' + configlist[4] + ' ' + configlist[2] + ' < $s; done && cd ' + configlist[6] + ' && ../../apache2/bin/restart')
        
    
def tweetIt():
    """
    Tweet any interesting things that pop up this week
    """
    
    """
    with open("../config.txt", "rb") as w:
         l = w.readlines()
    
    t = Twitter(auth=OAuth(
        configlist[9],
        configlist[10],
        configlist[11],
        configlist[12])
    ))
    
    text = "Pssst. Got a new batch of Nebraska campaign finance data in today: http://dataomaha.com/campaign-finance"
    
    pic = "https://media.giphy.com/media/qi8Yhj4pKcIec/giphy.gif"
    
    r = requests.get(pic, stream = True)
    if r.status_code == 200:
        r.raw.decode_content = True
        imagedata = r.raw.read()

        t_up = Twitter(domain='upload.twitter.com',
            auth=OAuth(
            configlist[9],
            configlist[10],
            configlist[11],
            configlist[12])
        ))
        
        id_img = t_up.media.upload(media=imagedata)["media_id_string"]
        
        t.statuses.update(status=text, media_ids=id_img)
    """