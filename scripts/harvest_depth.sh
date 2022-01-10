#!/bin/sh
DIR=$( cd "$(dirname "$0")" ; pwd -P )
. $DIR/env.sh
LIST=`mktemp`
LIST2=`mktemp`
http_proxy="" https_proxy=""

TMP_SEED=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 13 ; echo '')
HARVEST_CHECKED="/tmp/harvest_checked_$TMP_SEED"
HARVEST_NEW="/tmp/harvest_new_$TMP_SEED"
SCRAPE_CHECKED="/tmp/scrape_checked_$TMP_SEED"
SCRAPE_NEW="/tmp/scrape_new_$TMP_SEED"
TMP_TMP1="/tmp/tmp1_$TMP_SEED"
TMP_TMP2="/tmp/tmp2_$TMP_SEED"

echo "" > $HARVEST_CHECKED
echo "" > $SCRAPE_CHECKED
echo "$1" > $HARVEST_NEW


depth=0

while true; do # repeat unlimited

    depth=$((depth+1))
        
    cp $HARVEST_NEW $TMP_TMP1
    echo "" > $HARVEST_NEW

    if [ -s $TMP_TMP1 ]
    then
        echo "depth $depth started"
    else        
        echo "finishing..."
        break
    fi

    while IFS= read -r line1; do

        echo "checking $depth: $line1"
        lynx -listonly -dump  $line1 | awk '/^[ ]*[1-9][0-9]*\./{sub("^ [^.]*.[ ]*","",$0); print;}' | uniq | sort > $SCRAPE_NEW
        
        uniq $SCRAPE_NEW > $HARVEST_NEW  

        uniq $SCRAPE_NEW | grep -E -o '[\w\-\.]+\.onion' >> $LIST # add onions to harvest list
        uniq $SCRAPE_NEW | grep -E '[\w\-\.]+\.onion' >> $SCRAPE_CHECKED # add onions to checked
        uniq $SCRAPE_NEW > $TMP_TMP2  
        comm -13 $SCRAPE_CHECKED $TMP_TMP2 > $SCRAPE_NEW
        cat $SCRAPE_CHECKED $SCRAPE_NEW | uniq | sort > $TMP_TMP2
        cat $TMP_TMP2 > $SCRAPE_CHECKED
        
        while IFS= read -r line2; do
            echo "extracting  $depth: $line1 ($line2)"
            $SCRIPTDIR/extract_from_url.sh $line2 >> $LIST
        done < $SCRAPE_NEW
        
        $SCRIPTDIR/purify.sh $LIST > $LIST2
        NUMBER=`wc -l $LIST2 | tr -s ' ' | cut -f 1 -d ' '`
        echo "Harvested $NUMBER onion links..."
        $SCRIPTDIR/push_list.sh $LIST2
        rm $LIST $LIST2

    done < $TMP_TMP1

    uniq $HARVEST_NEW > $TMP_TMP1
    comm -13 $HARVEST_CHECKED $TMP_TMP1  > $HARVEST_NEW
    cat $HARVEST_CHECKED $HARVEST_NEW | uniq | sort > $TMP_TMP1
    cat $TMP_TMP1 > $HARVEST_CHECKED
    
done

rm $HARVEST_CHECKED
rm $HARVEST_NEW
rm $SCRAPE_CHECKED
rm $SCRAPE_NEW
rm $TMP_TMP1
rm $TMP_TMP2
