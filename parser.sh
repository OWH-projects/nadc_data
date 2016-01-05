#!/bin/bash

P=$(sed -n '6p' ../config.txt)
FUSER=$(sed -n '1p' ../config.txt)
FPW=$(sed -n '2p' ../config.txt)

#fetch the files, yo
printf "\n~~ fetching new data ~~\n"
mkdir -p ${P}nadc_data/toupload
wget http://www.nebraska.gov/nadc_data/nadc_data.zip
unzip -j -o nadc_data.zip
rm nadc_data.zip
chmod 777 *.txt *.TXT *.rtf
printf "~~ fetched 'at data ~~\n\n"

#parse the "last updated" date
printf "\n~~ parsing \"last updated\" date ~~\n"
fab getDate
\cp ${P}nadc_data/last_updated.py ${P}nadc/last_updated.py
printf "~~ parsed \"last updated\" date ~~\n\n"

#make backup copies of everything
printf "~~ making some backup files ~~\n"
mkdir -p ${P}nadc_data/backup
cp *.txt ${P}nadc_data/backup
printf "~~ made some backup files ~~\n\n"

#fix date formatting
printf "~~ fixing the date format ~~\n"
sed -i 's/\([0-9][0-9]\)\/\([0-9][0-9]\)\/\([0-9][0-9][0-9][0-9]\)/\3-\1-\2/g' *.txt
printf "~~ fixed the date format ~~\n\n"

#main script that parses raw data into tables for upload
printf "~~ doing all the things ~~\n"
fab parseErrything
#printf "~~ did all the things ~~\n\n"

#pick up after yourself
printf "~~ cleaning up ~~\n"
cd ${P}nadc_data/toupload/ && rm donations-raw.txt entity-raw.txt donations_almost_there.txt entities_sorted_and_deduped.txt entities_deduped.txt
printf "~~ cleaned up ~~\n\n"

# kill 'n' fill data locally
printf "~~ killing and filling new data ~~\n"
mysql --local-infile -u ${FUSER} -p${FPW} -e "DELETE FROM django_database.nadc_donation; DELETE FROM django_database.nadc_candidate; DELETE FROM django_database.nadc_loan; DELETE FROM django_database.nadc_expenditure; DELETE FROM django_database.nadc_entity; LOAD DATA LOCAL INFILE '${P}nadc_data/toupload/entity.txt' INTO TABLE django_database.nadc_entity FIELDS TERMINATED BY '|'; SET foreign_key_checks = 0; LOAD DATA LOCAL INFILE '${P}nadc_data/toupload/donations.txt' INTO TABLE django_database.nadc_donation FIELDS TERMINATED BY '|'; LOAD DATA LOCAL INFILE '${P}nadc_data/toupload/candidate.txt' INTO TABLE django_database.nadc_candidate FIELDS TERMINATED BY '|'; LOAD DATA LOCAL INFILE '${P}nadc_data/toupload/loan.txt' INTO TABLE django_database.nadc_loan FIELDS TERMINATED BY '|'; LOAD DATA LOCAL INFILE '${P}nadc_data/toupload/expenditure.txt' INTO TABLE django_database.nadc_expenditure FIELDS TERMINATED BY '|'; SET foreign_key_checks = 1;"
printf "~~ killed and filled new data ~~\n\n"

#run save method to untangle expenditure links
printf "~~ running save method on expenditures ~~\n"
cd ${P} && cd ..
python2.7 manage.py save_expenditures
printf "~~ ran save method on expenditures  ~~\n\n"

#restart fussy
printf "~~ restarting server ~~\n"
sudo service apache2 restart
printf "~~ server restarted ~~\n\n"

#generate SQL dumps for upload
printf "~~ baking out SQL files for Dataomaha ~~\n"
cd ${P}nadc_data/toupload
mysqldump -u ${FUSER} -p${FPW} django_database nadc_candidate | gzip > candidate.sql.gz
mysqldump -u ${FUSER} -p${FPW} django_database nadc_loan | gzip > loan.sql.gz
mysqldump -u ${FUSER} -p${FPW} django_database nadc_donation | gzip > donation.sql.gz
mysqldump -u ${FUSER} -p${FPW} django_database nadc_entity | gzip > entity.sql.gz
mysqldump -u ${FUSER} -p${FPW} django_database nadc_expenditure | gzip > expenditure.sql.gz
printf "~~ baked out SQL files for Dataomaha ~~\n\n"

#upload sql dump + last_updated.py to live server
printf "~~ dropping files on Dataomaha ~~\n"
cd ${P}nadc_data
fab goLive
printf "~~ dropped files on Dataomaha ~~\n\n"

#tweet
#printf "~~ tweeting ~~\n"
#printf "~~ tweeted ~~\n\n"

printf "~~ DONE ~~\n\n"