#!/bin/bash

# Clear crawler output files from all crawlers
rm /data/crawlerOutput/chromeProfile/*
rm /data/crawlerOutput/safariProfile1/*
rm /data/crawlerOutput/safariProfile1Copy/*
rm /data/crawlerOutput/safariProfile2/*

# Clear cookies, storage, and crawlEvent files from all crawlers
rm /data/test_results/safariProfile1/cookies/*
rm /data/test_results/safariProfile1/localStorage/*
rm /data/test_results/safariProfile1/crawlEvents/*
rm /data/test_results/safariProfile1/extensionRequests/*

rm /data/test_results/safariProfile2/cookies/*
rm /data/test_results/safariProfile2/localStorage/*
rm /data/test_results/safariProfile2/crawlEvents/*
rm /data/test_results/safariProfile2/extensionRequests/*

rm /data/test_results/chromeProfile/cookies/*
rm /data/test_results/chromeProfile/localStorage/*
rm /data/test_results/chromeProfile/crawlEvents/*
rm /data/test_results/chromeProfile/extensionRequests/*

rm /data/test_results/safariProfile1Copy/cookies/*
rm /data/test_results/safariProfile1Copy/localStorage/*
rm /data/test_results/safariProfile1Copy/crawlEvents/*
rm /data/test_results/safariProfile1Copy/extensionRequests/*

rm /data/list_of_failed_crawls.csv


# Old folders
# rm /big_data/test_results/safariProfile1/cookies/*
# rm /big_data/test_results/safariProfile1/localStorage/*
# rm /big_data/test_results/safariProfile1/crawlEvents/*

# rm /big_data/test_results/safariProfile2/cookies/*
# rm /big_data/test_results/safariProfile2/localStorage/*
# rm /big_data/test_results/safariProfile2/crawlEvents/*

# rm /big_data/test_results/chromeProfile/cookies/*
# rm /big_data/test_results/chromeProfile/localStorage/*
# rm /big_data/test_results/chromeProfile/crawlEvents/*

# rm /big_data/test_results/safariProfile1Copy/cookies/*
# rm /big_data/test_results/safariProfile1Copy/localStorage/*
# rm /big_data/test_results/safariProfile1Copy/crawlEvents/*