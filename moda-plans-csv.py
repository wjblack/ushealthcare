#!/usr/bin/python3

"""
	Simple script to screenscrape the list of Moda Health plans and return a CSV of plan details.

	Prereqs:  Python3 and requests (installed on most modern python systems by default)

	Usage:
		moda-plans-csv.py 97103 --self Foobar 1/2/2000 --spouse Barfoo 2/1/2000 --child Foobarfoo 1/1/2020 > foo.csv

	Moda's website, like many eCommerceish sites, is a maze of trackers and analytics stuff, but the application basically is:
	1. See what the county/state stuff is (the LOCALITY call).  I also do a TRIAGE call, but that's *probably* unnecessary.
	2. Set the session to the user info (the INTAKE call), and finally
	3. Grab the list of plans (the MEDICAL_PLANS call), which has a one-liner JSON blob with all the actual data in it.

	You could *probably* get away without explicitly doing #1, but you really need #2 to inject the appropriate data into
	the session so that #3 doesn't just redirect you back to the main page.

	This blob looks like:
		FME.PLANCARDDISPLAY.PlansInitialData = {"TotalMedicationsCount":0,...};
	So it's just a matter of ripping out everything on the RHS of that equals sign, stripping off the unnecessary semicolon,
	and decoding it as JSON.  Once you have that, you get a reasonable python object that's easy enough to convert to CSV.

	And yes, this script working is subject to the whims of the website admin.  If there were an API (and there will never be,
	because competition and I'm strictly-speaking scraping their website which they don't like), I'd use it.

	Script (C) 2022 by BJ Black <bj@wjblack.com>
	Licensed to the world under the WTFPL (http://wtfpl.net) with NO WARRANTY--hopefully this is useful to someone.
"""

import csv
import json
import re
import requests
import sys
import time # FIXME
from dateutil import parser

MODA_LOCALITY_URL = "https://www.modahealth.com/shop/api/Zipcode/search/?q="
MODA_TRIAGE_URL = "https://www.modahealth.com/shop/api/ContextService/settriageEx"
MODA_INTAKE_URL = "https://www.modahealth.com/shop/api/ContextService/Intake"
MODA_PLANS_URL = "https://www.modahealth.com/shop/plans/medical-plans"

session = requests.Session()

class People:
	insured = None
	spouse = None
	children = None

	def add(self, data):
		if len(data) != 3:
			raise ValueError("Invalid person entry: %s" % str(data))
		person = dict(FirstName=data[1], DateOfBirth=normalize_date(data[2]), PersonId=None)
		if data[0] == "--self":
			person["Type"] = 1
			self.insured = person
		elif data[0] == "--spouse":
			person["Type"] = 2
			self.spouse = person
		elif data[0] == "--child":
			person["Type"] = 3
			if self.children == None:
				self.children = [person]
			else:
				self.children.append(person)
		else:
			raise ValueError("Unknown person type: %s" % str(data[0]))

	def covered(self):
		"""
			Spit back an array of CoveredPersons suitable for ingest into INTAKE.
		"""
		ret = dict()
		if self.insured is None and self.spouse is not None:
			raise ValueError("Must have insured set when spouse is set.")
		if self.insured is None and self.spouse is None:
			if self.children is None:
				raise ValueError("Must have at least either insured set or >= child set.")
			else:
				ret["OnlyChildCoverage"] = True
		covered = []
		if self.insured is not None:
			covered.append(self.insured)
		if self.spouse is not None:
			covered.append(self.spouse)
		if self.children is not None:
			for child in self.children:
				covered.append(child)
		ret["CoveredPersons"] = covered
		return ret

def normalize_date(date):
	return parser.parse(date).strftime("%m/%d/%Y")

def set_locality(zipcode="97103"):
	"""
		Get the appropriate locality info from Moda and then execute their settriageEx to save it to the session.
	"""
	res = session.get(MODA_LOCALITY_URL + zipcode)
	locality_res = res.json()
	locality = locality_res["zipCodes"][0]
	zipcode, county, state = locality["Zip"], locality["County"], locality["State"]
	data = dict(ZipCode=zipcode, County=county, StateCode=state, IsCurrentMember=False, KeepData=False)
	res = session.post(MODA_TRIAGE_URL, json=data)
	services = res.json()
	if not services["HasMedicalServiceArea"]:
		raise ValueError("Medical plans not available in %s, %s, %s" % (zipcode, county, state))
	return zipcode, county, state

def set_coverage(zipcode, people):
	"""
		Set the intake data, so the session knows the names/ages of the covered persons.
		Obviously it doesn't really say anywhere, so I assume that Self is type=1, Spouse is type=2 and Dependents are
		type=3, but that's a total guess.
	"""
	zipcode, county, state = set_locality(zipcode)
	data = dict(
		County=county,
		CoveredPersonsRequest=people.covered(),
		Shopper="0",
		StateCode=state,
		ZipCode=zipcode
	)
	res = session.post(MODA_INTAKE_URL, json=data)
	return res.json

def get_plans(zipcode, people):
	"""
		Fetch the contents of Moda's sales site and spit back the data embedded therein as a set of rows.
	"""
	set_coverage(zipcode, people)
	res = session.get(MODA_PLANS_URL)
	plancardre = re.compile(r'PlansInitialData\s*=\s*(\S+.*);')
	matches = plancardre.search(res.text, re.MULTILINE)
	if matches is not None:
		return json.loads(matches.group(1))
	raise ValueError("Couldn't find PlansInitialData in output.")

def get_plans_csv(zipcode, people, output):
	resultset = get_plans(zipcode, people)
	writer = csv.writer(output)
	cols = None
	for result in resultset["Results"]:
		plan = result["Plan"]
		if cols is None:
			cols = dict(Name=0, Rate=1)
			row = ["Name", "Rate"]
			i = 2
			for key in plan:
				if key == "Name":
					continue
				row.append(key)
				cols[key] = i
				i += 1
			writer.writerow(row)
		row = [None] * len(cols)
		i = 0
		if "Name" in plan:
			row[i] = plan["Name"]
			i += 1
		row[i] = result["Rate"]
		i += 1
		for key in plan:
			if key == "Name":
				continue
			try:
				row[cols[key]] = plan[key]
			except:
				print("Exception: ", key, cols[key])
		writer.writerow(row)


if __name__ == "__main__":
	zipre = re.compile(r'^\d{5}$')
	if len(sys.argv) == 1 or sys.argv[1] == "--help" or not zipre.match(sys.argv[1]):
		print("Usage: %s <zipcode> " % sys.argv[0])
		print("       %s [--self <first_name> <dob>]" % (" "*len(sys.argv[0])))
		print("       %s [--spouse <first_name> <dob>]" % (" "*len(sys.argv[0])))
		print("       %s [--child <first_name> <dob>]" % (" "*len(sys.argv[0])))
		print("       %s [--child <first_name> <dob>]" % (" "*len(sys.argv[0])))
		print("       %s [--child <first_name> <dob>]" % (" "*len(sys.argv[0])))
		print("       %s ..." % (" "*len(sys.argv[0])))
		sys.exit(0)

	zipcode = sys.argv[1]
	people = People()
	person = None
	for arg in sys.argv[2:]:
		if person is not None and len(person) == 3:
			people.add(person)
			person = None
		if person is None and arg in ["--self", "--spouse", "--child"]:
			person = [arg]
		elif person is not None:
			person.append(arg)
	if person is not None and len(person) == 3:
		people.add(person)

	get_plans_csv(zipcode, people, sys.stdout)
