# Comparison Shopping for US Healthcare Plans

## Introduction

These python scripts are used to do web scraping of various health care providers'
websites to get rates and coverage summaries so you don't have to go nuts compiling
this information yourself.  For the most part, they output a spreadsheet-friendly
CSV with whatever info the sites have.

## Usage

Moda's gotten done first, so here goes:

`./moda-plans-csv.py 78746 --self Foo 1/1/1990 --spouse Bar 2/2/1989 --child Baz 3/3/2010 > moda.csv`

Basically you feed it a ZIP code and name/birthday for whoever's getting insured and you get a CSV
dump of whatever's on their website.

## Architecture

Are you kidding?  These are "scratch a personal itch" programs and aren't intended to be a service.
They're hackjobs and they're very likely to break without notice as the vendor changes the website.
But as of the time I'm typing this, they work :-)
