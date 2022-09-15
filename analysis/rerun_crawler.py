import csv
import subprocess
import json
from datetime import datetime, timedelta
import os
from publicsuffix2 import get_sld

unzipped_profile_path = '/data/tmp_redo_profile/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/tmpProfileCookiesDisabled'

def getProfiles():
    byte_str = subprocess.run(["ls", "/big_data/profiles"], capture_output=True).stdout
    profile_str = str(byte_str, 'utf-8')
    profiles = profile_str.splitlines(keepends=False)
    return profiles

def parseRedirectChains(filename, use_same_profile):
    used_redirect_chains = []
    profiles = getProfiles()

    f = open(filename, 'r')
    reader = csv.DictReader(f, quotechar='`')
    for row in reader:
        urls_in_redirect_chains = row['urls_in_redirect_chains']
        seeder_domain = row['seeder_domain']
        start_url = row['start_url']
        # start_url = row['src_top_level_frame_domain']
        redirect_chain_id = str(row['redirect_chain_id'])
        if redirect_chain_id in used_redirect_chains:
            continue
        used_redirect_chains.append(redirect_chain_id)
        profile = ''
        if not use_same_profile:
            runRedoCrawler(redirect_chain_id, seeder_domain, start_url, urls_in_redirect_chains, profile, False)
            continue
        
        for p in profiles:
            if seeder_domain in p:
                if profile:
                    print("Multiple profiles found for ", seeder_domain)
                profile = p
        runRedoCrawler(redirect_chain_id, seeder_domain, start_url, urls_in_redirect_chains, profile, True)

def runRedoCrawler(redirect_chain_id, seeder_domain, start_url, urls_in_redirect_chains, profile, use_same_profile):
    # Copy profile to a tmp profile
    if use_same_profile:
        success = subprocess.run(['./analysis/copy_tmp_profile.sh', profile])
        if success.returncode:
            print('Failed to create tmp profile:', success.returncode)
    else:
        success = subprocess.run(['./analysis/create_blank_profile.sh'])
        if success.returncode:
            print('Failed to create tmp profile:', success.returncode)


    # redirect_chain_id, seeder_domain, start_url, document_request_urls, profile
    print("Starting rerun_crawler.js for start url ", start_url)
    # success = subprocess.run(['node', 'rerun_crawler.js', redirect_chain_id, seeder_domain, start_url, urls_in_redirect_chains, unzipped_profile_path])
    success = subprocess.run(['node', 'rerun_crawler.js', redirect_chain_id, seeder_domain, start_url, urls_in_redirect_chains, 'tmp_profile'])
    if success.returncode:
        print("Rerun_crawler.js exited with non-zero status", success.returncode)
    print("Finished rerun_crawler.js?")

def redoFailedCrawl(filename):
    profiles = getProfiles()
    f = open(filename, 'r')
    for line in ['{"redirect_chain_id":"irs.gov_4","seeder_domain":"irs.gov","document_request_urls":["https://play.google.com/store/apps/details?id=com.instagram.android&referrer=utm_source%3Dinstagramweb&utm_campaign=loginPage&ig_mid=FC155609-B5C7-4F85-8335-232573FA702B&utm_content=lo&utm_medium=badge"],"start_url":"https://www.irs.gov/privacy-disclosure/irs-privacy-policy","seconds":120,"debug":true,"profile":"/big_data/tmp_redo_profile/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/tmpProfileCookiesDisabled","chromePath":"/usr/bin/google-chrome-stable"}']:  # f:
        args = json.loads(line)
        profile = ''
        for p in profiles:
            if args['seeder_domain'] in p:
                if profile:
                    print("Multiple profiles found for ", args['seeder_domain'])
                profile = p
        runRedoCrawler(args['redirect_chain_id'], args['seeder_domain'], args['start_url'], ','.join(args['document_request_urls']), profile)
        break


####################################
### Analyze redone results #########
####################################

def uniqueChainIds():
    filename = '/big_data/redirect_chains/redirect_chains.txt'
    redirect_chain_ids = {}
    src_domains = {}
    dst_slds = {}
    already_used_rids = []

    f = open(filename, 'r')
    reader = csv.DictReader(f, quotechar='`')
    for row in reader:
        rid = row['redirect_chain_id']
        if rid in already_used_rids:
            continue
        already_used_rids.append(rid)
        src_domain = row['src_domain']
        dst_domain = row['dst_domain']
        dst_sld = get_sld(dst_domain)
        if dst_sld == 'google-analytics.com':
            print('RID:', rid)
        if dst_sld not in dst_slds:
            dst_slds[dst_sld] = 0
        dst_slds[dst_sld] += 1
        if src_domain not in src_domains:
            src_domains[src_domain] = 0
        src_domains[src_domain] += 1
        if rid not in redirect_chain_ids:
            redirect_chain_ids[rid] = []
        redirect_chain_ids[rid].append(row['src_top_level_frame_domain'])
    
    double_insta = 0
    for rid in redirect_chain_ids:
        # if rid == 'rakuten.co.jp_2':
        #     print(len(redirect_chain_ids[rid]))
        #     return
        if len(redirect_chain_ids[rid]) == 1:
            continue
        if len(redirect_chain_ids[rid]) > 2:
            # if redirect_chain_ids[rid][-1] != 'instagram.com':
            #     print(rid, redirect_chain_ids[rid])
            continue
        # if redirect_chain_ids[rid][0] != redirect_chain_ids[rid][1]:
        #     if redirect_chain_ids[rid][1] != 'instagram.com':
        #         print(rid, redirect_chain_ids[rid])
        #     else:
        #         double_insta += 1
        #print(rid, redirect_chain_ids[rid])
    total_src_domains = 0
    # for src_domain, num in sorted(src_domains.items(), key=lambda item: item[1], reverse=True):
    #     print(src_domain, num)
    #     total_src_domains += num 
    print('Total src_domains:', total_src_domains)
    for sld in dst_slds:
        print(sld, dst_slds[sld])

def analyzeFailedClick():
    f = open('/big_data/failed_finding_element_to_click.txt', 'r')
    instagram_login = set([])
    first_urls = set([])
    blank_first_urls = 0
    num_chains = 0
    for line in f:
        args = json.loads(line)
        # if len(args['document_request_urls']) > 1:
        #     print('More than one URL for', args['redirect_chain_id'])
        is_instagram = False
        for url in args['document_request_urls']:
            if 'https://play.google.com/store/apps/details?id=com.instagram.android' in url:
                instagram_login.add(args['redirect_chain_id'])
                is_instagram = True
                break
        if is_instagram:
            continue
        first_url = args['document_request_urls'][0].split('?')[0]
        first_urls.add(first_url)
        if first_url == '':
            blank_first_urls += 1
        num_chains += 1
        print(args['start_url'], first_url)
    print(blank_first_urls, num_chains)


def crawlerOutputFiles():
    f = open('/big_data/redirect_chains/redirect_chains.txt', 'r')
    reader = csv.DictReader(f)
    line_num = 1
    line_num_to_domain_date = {}
    for row in reader:
        seeder_domain = row['seeder_domain']
        # 2021-08-20 22:29:18.971000
        ts = datetime.strptime(row['src_ts'], "%Y-%m-%d %H:%M:%S.%f")
        date_str = row['src_ts'].split(' ')[0]
        line_num_to_domain_date[line_num] = (seeder_domain, date_str)
        line_num += 1

    f.close()
    line_num_to_crawler_output = {}
    for filename in os.listdir('/data/crawlerOutput'):
        date_str = filename.split('_')[0]
        try:
            seeder_domain = filename.split('_')[2].replace('.out', '')
        except IndexError:
            print('Filename formatted incorrectly:', filename)
            continue
        for tmp_line_num in line_num_to_domain_date:
            (s, d) = line_num_to_domain_date[tmp_line_num]
            if s == seeder_domain and d == date_str:
                line_num_to_crawler_output[tmp_line_num] = filename
                break
    return line_num_to_crawler_output

def compareOriginalRedirectChainToRedoneChain(redone_file):
    original = open('/big_data/redirect_chains/redirect_chains.txt', 'r')
    redone = open(redone_file, 'r')
    redone_rows = []
    
    reader = csv.DictReader(redone, quotechar='`')
    for row in reader:
        redone_rows.append(row)
    
    matches = []
    non_matches = []
    orig_line = 1
    reader = csv.DictReader(original, quotechar='`')
    for row in reader:
        orig_line += 1
        seeder_domain = row['seeder_domain']
        start_url = row['start_url']
        value = row['src_value']
        ts = row['src_ts']
        name = row['src_name']
        chain_id = row['redirect_chain_id']

        redo_line = 1
        found_match = False
        failed_to_redo = True
        for redone_row in redone_rows:
            redo_line += 1
            # if seeder_domain == redone_row['seeder_domain'] and start_url == row['start_url']:
            if chain_id == redone_row['original_chain_id']:
                failed_to_redo = False
                if value == redone_row['src_value'] and name == redone_row['src_name']:
                    match = {'seeder_domain': seeder_domain, 'start_url': start_url, 'value': row['src_value'], 'chain_id': chain_id}
                    matches.append(match)
                    found_match = True
                    break
        if not found_match and not failed_to_redo:
            non_match = {'src_ts': ts, 'seeder_domain': seeder_domain, 'start_url': start_url, 'value': value, 'name': name, 'orig_line': orig_line, 'chain_id': chain_id}
            non_matches.append(non_match)

    print('Matches:', len(matches), 'Non-matches:', len(non_matches))
    # for match in matches:
    #     print(match)
    return matches, non_matches

def whyAreThingsMissing():
    redone_file = '/big_data/redo_results/redirect_chains_redone_with_same_profile.txt'
    original = open('/big_data/redirect_chains/redirect_chains.txt', 'r')
    redone = open(redone_file, 'r')
    redone_ids = set([])
    original_ids = set([])
    
    reader = csv.DictReader(redone, quotechar='`')
    total_redone_ids = []
    for row in reader:
        redone_ids.add(row['original_chain_id'])
        total_redone_ids.append(row['original_chain_id'])

    reader = csv.DictReader(original, quotechar='`')
    for row in reader:
        original_ids.add(row['redirect_chain_id'])

    print('IDs in original but not in redone:', len(original_ids.difference(redone_ids)))
    print('Total original ids:', len(original_ids), ' Total redone ids:', len(redone_ids), 'Total redone IDS with repeats:', len(total_redone_ids))
    print('IDs in redone but not in original:', len(redone_ids.difference(original_ids)))
    print('Now what about run #2?')

    redone_file = '/big_data/redo_results/redirect_chains_redone_with_same_profile.txt'
    redone = open(redone_file, 'r')
    redone_ids = set([])

    reader = csv.DictReader(redone, quotechar='`')
    total_redone_ids = []
    for row in reader:
        redone_ids.add(row['original_chain_id'])
        total_redone_ids.append(row['original_chain_id'])

    print('Total redone IDs:', len(redone_ids))

def getUserIdentifiers():
    clean_redo = '/big_data/redo_results/redirect_chains_redone_with_clean_profile.txt'
    same_redo = '/big_data/redo_results/redirect_chains_redone_with_same_profile.txt'
    clean_matches, clean_non_matches = compareOriginalRedirectChainToRedoneChain(clean_redo)
    same_matches, same_non_matches = compareOriginalRedirectChainToRedoneChain(same_redo)
    user_ids = set([])
    non_user_ids = set([])

    clean_match_ids = set([c['chain_id'] for c in clean_matches])
    clean_nonmatch_ids = set([c['chain_id'] for c in clean_non_matches])
    same_match_ids = set([s['chain_id'] for s in same_matches])
    same_nonmatch_ids = set([s['chain_id'] for s in same_non_matches])
    clean_ids = clean_match_ids.union(clean_nonmatch_ids)
    same_ids = same_match_ids.union(same_nonmatch_ids)

    print('IDs in both the clean profile and same profile reruns:', len(clean_ids.intersection(same_ids)), 'Total unique IDs:', len(clean_ids.union(same_ids)))
    print('Total IDs including repeats')

    # If a redirect chain is in clean_non_matches and same_matches, it's a user ID
    for clean_non_match in clean_non_matches:
        chain_id = clean_non_match['chain_id']
        for same_match in same_matches:
            if chain_id == same_match['chain_id']:
                user_ids.add(chain_id)
    # for (chain_id, value) in user_ids:
    #     print(chain_id, value)

    print('Redirect chains that contain a user ID, unless they have one token in clean_non_matches and a different token in same_matches:', len(user_ids))

# Before running this, run analyze.py to generate redirect_chains.txt. 
# parseRedirectChains('/big_data/redirect_chains/test_redirect_chains.txt', True)
#redoFailedCrawl('/big_data/failed_finding_element_to_click.txt')

#line_num_to_crawler_output = crawlerOutputFiles()
# compareOriginalRedirectChainToRedoneChain()
# analyzeFailedClick()
# getUserIdentifiers()

# clean_redo = '/big_data/redo_results/redirect_chains_redone_with_clean_profile.txt'
# # same_redo = '/big_data/redo_results/redirect_chains_redone_with_same_profile.txt'
# clean_matches, clean_non_matches = compareOriginalRedirectChainToRedoneChain(clean_redo)
# whyAreThingsMissing()
uniqueChainIds()