#NADC data

Scripts to process data from the Nebraska Accountability and Disclosure Commission into something <a href="https://github.com/OWH-projects/nadc">our campaign finance app</a> can import. Run `pip install -r requirements.txt` to install the dependencies:
- [csvkit](https://csvkit.readthedocs.org/en/0.9.1/)  
- [pandas!](http://pandas.pydata.org/pandas-docs/stable/)  
- [fabric](http://www.fabfile.org/)

The NADC now offers <a href="http://www.nebraska.gov/data.html" target="_blank">weekly updates</a> of campaign finance data. Every Monday, our script fetches new data, parses it and returns a set of clean files that our app can ingest. The update process:
<ol>
<li>Run <code>./parser.sh</code></li>
<li>If there are new, invalid dates that we haven't encountered in the past, you'll be prompted to add those to <code>canonical/canonical.py</code></li>
</ol>

##Overview
A standard data dump from the NADC yields 61 pipe-delimited text files (data dictionary at: `nadc_tables.rtf`). We extract data from 24 of them:
<ul>
<li><strong>Form A1</strong>: Lookup table for most committees</li>
<li><strong>Form A1CAND</strong>: Candidates tied to campaign committees</li>
<li><strong>Form B1</strong>: Campaign statements for candidate or ballot question committees</li>
<li><strong>Form B1AB</strong>: Main table of individual/other contributions</li>
<li><strong>Form B1C</strong>: Loans to campaign committees</li>
<li><strong>Form B1D</strong>: Expenditures by campaign committees</li>
<li><strong>Form B2</strong>: Campaign statements for political party committees</li>
<li><strong>Form B2A</strong>: Contributions to political party committees</li>
<li><strong>Form B2B</strong>: Expenditures by political party committees</li>
<li><strong>Form B4</strong>: Campaign statements for independent committees</li>
<li><strong>Form B4A</strong>: Contributions to independent committees</li>
<li><strong>Form B4B1</strong>: Expenditures by independent committees</li>
<li><strong>Form B4B2</strong>: Federal and out-of-state disbursements</li>
<li><strong>Form B4B3</strong>: Administrative/operating disbursements</li>
<li><strong>Form B5</strong>: Late contributions</li>
<li><strong>Form B6</strong>: Reports of an independent expenditure or donation made by people or entities that are not registered as committees</li>
<li><strong>Form B6EXPEND</strong>: Expenditures made on behalf of committees by people who do not have an ID</li>
<li><strong>Form B7</strong>: Registration of corporations, unions and other associations</li>
<li><strong>Form B72</strong>: Donations by corporations, unions and other associations</li>
<li><strong>Form B73</strong>: Indirect contributions by corporations, unions and other associations</li>
<li><strong>Form B9</strong>: Out of state expenditures/donations</li>
<li><strong>Form B9B</strong>: Out of state expenditures</li>
<li><strong>Form B11</strong>: Report of late independent expenditure</li>
</ul>

A shell script, `parser.sh`, makes backups of the raw data and boils down these 24 files (which contain some duplicate transactions) into five data tables:
<ul>
<li><code>toupload/entity.txt</code>: Any group, committee, donor, lender or other entity that has been assigned a unique ID by the NADC. This is the parent table.</li>
<li><code>toupload/donations.txt</code>: Money, inkind donations and pledges.</li>
<li><code>toupload/candidates.txt</code>: Candidates tied to campaign committees and ballot questions.</li>
<li><code>toupload/loans.txt</code>: Lending.</li>
<li><code>toupload/expenditures.txt</code>: Expenditures.</li>
</ul>

Then, the script bakes out some SQL to upload to our live server.

##Handling duplication
###Names
NADC has unique identifiers for each donor, but they identify only the address and exact name. If "Matt Wynn" at 1314 Douglas St. gave money, and "Matthew A Wynn" at 1300 Douglas St. gave money, they're considered two different donors.

This is wrong.

We can't deduplicate every donor, so our solution was to create a lookup dictionary (The "CANON" variable in `canonical/canonical.py`) for any "large" donors, whether in terms of total donations or the number of donations. Super fellow [Daniel Wheaton](https://twitter.com/theheroofthyme) assigned new, real unique identifiers for any of the top 100 donors by both measures. Those lists overlapped a bit, so we wound up deduplicating around 70 donors on the first pass. This is why each entity has two ids, with canonical_id representing our assignment of an identity.

The NADC ID is copied to canonical_id for records that are not deduplicated. Same with the name.

###Donations
Some donations are recorded in several places. A late donation, for instance, may also show up as a normal donation record in B1AB.

Donations can also be duplicated within a table, inaccurately. For example, a 1999 ballot committee reported each of its donations twice, leading to a vastly inflated fundraising report.

Susan Lorenz at the Nebraska Accountability and Disclosure Commission told us that donations from a giver to an organization on the same day should not be duplicated. Therefore, we deduplicated using those three values.

##Known problems
###Dates
Some records have invalid dates. We added these to a python dictionary in `nadc/data/canonical/canonical.py` and they get fixed on import.

We can't predict the ways dates will be screwed up in the future. Any invalid dates that don't already exist in our lookup get printed to the screen mid-script for you to fix later.

###Purposeful duplication
To get an exhaustive list of ID'd entities, the script slurps up a half-million records and reduces them to a file about a tenth that size. We use pandas' [`drop_duplicates`](http://pandas.pydata.org/pandas-docs/stable/generated/pandas.DataFrame.drop_duplicates.html) function, grep and python to ensure to return a set of deduplicated records with the most recent, comprehensive data.

##Data excluded
<ul>
<li>Pre-1999 records, which the NADC does not consider especially reliable.</li>
<li><code>Form B6CONT</code>, part of a group of cleanup files for expenditures that aren't recorded elsewhere. It is a garbage fire.</li>
<li>Records associated with candidate committee No. 99CAC00167, Friends of Doug Kristensen, which was related to Mr. Kristensen's candidacy for a delegate slot at the 1996 Republican National Convention. As far as we can tell, this is the only time a candidacy for party delegate shows up in the data.</li>
</ul>