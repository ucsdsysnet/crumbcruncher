#!/bin/bash

profile_1="/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/safariProfile1"
profile_1_copy="/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/safariProfile1copy"
profile_2="/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/safariProfile2"
chrome_profile="/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/chromeProfile"

# Delete the old profiles
rm -r $profile_1
rm -r $profile_2
rm -r $chrome_profile

# Create the new profiles
cd /
cp -r "/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/Default" $profile_1
cp -r "/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/Default" $profile_2
cp -r "/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/Default" $chrome_profile

# Run all of the crawlers
ds=`date '+%Y-%m-%d_%H-%M-%S'`

cd "/home/ec2-user/brave-redirection-recorder"

# Start the controller
node lib/controller & 
controller_pid=$!

# node test.js "https://$1" $profile_1 > /data/crawlerOutput/safariProfile1/$1_$ds.txt &
# node test.js "https://$1" $profile_2 > /data/crawlerOutput/safariProfile2/$1_$ds.txt &
# node test.js "https://$1" $chrome_profile > /data/crawlerOutput/chromeProfile/$1_$ds.txt &

node test.js "https://$1" $profile_1 > tmp1.txt &
pid_1=$!
node test.js "https://$1" $profile_2 > tmp2.txt &
pid_2=$!
node test.js "https://$1" $chrome_profile > tmp3.txt &
pid_3=$!

# Wait for them to finish
wait $pid_1
wait $pid_2
wait $pid_3

# Now run the fourth crawler, that uses a copy of safariProfile1
# Copy safariProfile1
cp -r $profile_1 $profile_1_copy
node rerun_crawler.js $line $profile_1_copy > tmp4.txt

# Clear profile_1_copy 
rm -r $profile_1_copy

# Stop the controller
kill $controller_pid