#!/bin/bash

# rm -r old_results 
# mv results old_results
# mkdir results
# mkdir results/cookies
# mkdir results/crawlEvents
# mkdir results/localStorage

while read -r line; do 
    date=`date '+%Y-%m-%d_%H-%M-%S'`

    # Copy the third-party-cookies-blocked profile
    cp -r "/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/Default" "/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/tmpProfileCookiesDisabled"

    # Run the crawler
    cd "/home/ec2-user/brave-redirection-recorder"
    node test.js "https://$line" > "/data/crawlerOutput/${date}_${line}.out"

    # Save the profile and delete the tmp directory
    tar -zcf "/big_data/profiles/${date}_${line}_profile.tar.gz" "/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/tmpProfileCookiesDisabled"
    rm -r "/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/tmpProfileCookiesDisabled"
done < /home/ec2-user/brave-redirection-recorder/tranco_top_1m_truncated.csv
