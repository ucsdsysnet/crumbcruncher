#!/bin/bash

host=brave1

# Run these commands on Taliesin
scp ~/.ssh/github $host:~/.ssh/github
scp ~/tranco_domains/tranco_$host.csv $host:tranco_top_1m.csv
scp ~/tranco_domains/default.tar.gz $host:
scp ~/tranco_domains/google-chrome.repo $host:

# Run these commands on the ec2 instance
sudo yum update

# Install Git
sudo yum install git

# Install Chrome
sudo mv google-chrome.repo /etc/yum.repos.d/
sudo yum install google-chrome-stable

# Move the third-party-cookies-disabled profile to the right place and untar it
mkdir /home/ec2-user/.config
mkdir /home/ec2-user/.config/google-chrome
mkdir /home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/
tar -xf default.tar.gz --directory /home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/

# Make a filesystem on the storage volume
sudo mkfs -t xfs /dev/xvdf
# Mount the storage volume
sudo mkdir /data
sudo mount /dev/xvdf /data/
sudo chown ec2-user:ec2-user /data
sudo chmod a+w /data

# Create the folder structure for output
sudo mkdir /data/crawlerOutput
sudo mkdir /data/crawlerOutput/chromeProfile
sudo mkdir /data/crawlerOutput/safariProfile1
sudo mkdir /data/crawlerOutput/safariProfile1Copy
sudo mkdir /data/crawlerOutput/safariProfile2
sudo mkdir /data/test_results
sudo mkdir /data/test_results/safariProfile1
sudo mkdir /data/test_results/safariProfile1Copy
sudo mkdir /data/test_results/safariProfile2
sudo mkdir /data/test_results/chromeProfile
sudo mkdir /data/test_results/chromeProfile/cookies
sudo mkdir /data/test_results/chromeProfile/localStorage
sudo mkdir /data/test_results/chromeProfile/crawlEvents
sudo mkdir /data/test_results/safariProfile1/cookies
sudo mkdir /data/test_results/safariProfile1/crawlEvents
sudo mkdir /data/test_results/safariProfile1/localStorage
sudo mkdir /data/test_results/safariProfile1Copy/cookies
sudo mkdir /data/test_results/safariProfile1Copy/crawlEvents
sudo mkdir /data/test_results/safariProfile1Copy/localStorage
sudo mkdir /data/test_results/safariProfile2/cookies
sudo mkdir /data/test_results/safariProfile2/crawlEvents
sudo mkdir /data/test_results/safariProfile2/localStorage
sudo mkdir /data/test_results/redo_files

# For good measure
sudo chmod -R a+w /data

# Install XVFB
sudo yum install xorg-x11-server-Xvfb
Xvfb :99 &
export DISPLAY=:99

# Install nvm (npm?) and nodejs
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.34.0/install.sh | bash
. ~/.nvm/nvm.sh
nvm install node

# Install packages
npm install puppeteer-extra

eval $(ssh-agent)
ssh-add ~/.ssh/github
git clone git@github.com:brave-experiments/brave-redirection-recorder.git
mv ~/tranco_top_1m.csv brave-redirection-recorder/
cd brave-redirection-recorder
git checkout audrey-ec2



# Somehow need to copy the right profiles from machine to machine

