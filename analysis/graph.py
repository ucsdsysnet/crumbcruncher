import json 
import csv
import matplotlib.pyplot as plt
import requests
import pandas as pd

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['pdf.fonttype'] = 42
plt.rcParams['ps.fonttype'] = 42
import numpy as np
from publicsuffix2 import get_sld
import os

def uidCertaintyLevel(filename):
    f = open(filename, 'r')
    two_of_three = ['safariProfile1', 'safariProfile2', 'chromeProfile']
    certainty = {}
    crawlers_by_token = {}
    unique_tokens = set([])
    for line in f:
        result = json.loads(line)
        crawlers = result['crawlers_where_token_name_was_seen']
        token = result['token']
        if token not in certainty:
            certainty[token] = set([])
        crawlers_by_token[token] = crawlers
        num_different_crawlers = 0
        for c in two_of_three:
            if c in crawlers:
                num_different_crawlers += 1
        if num_different_crawlers >= 2:
            if 'safariProfile1Copy' in crawlers and 'safariProfile1' in crawlers and ('safariProfile2' in crawlers or 'chromeProfile' in crawlers):
                unique_tokens.add(token)
                certainty[token].add('all_three')
            else:
                certainty[token].add('different_crawlers_only')
        elif num_different_crawlers == 1:
            if 'safariProfile1Copy' in crawlers:
                if 'safariProfile1' in crawlers:
                    certainty[token].add('same_crawlers_only')
                else:
                    certainty[token].add('different_crawlers_only')
            else:
                certainty[token].add('only_one_crawler')
        else:
            certainty[token].add('only_one_crawler')

        if certainty[token] == 'all_three':
            unique_tokens.add(token)

    certainty_counts = {
        'all_three': 0,
        'different_crawlers_only': 0,
        'same_crawlers_only': 0,
        'only_one_crawler': 0
    }
    for token in certainty:
        for c in certainty[token]:
            certainty_counts[c] += 1
    for c in certainty_counts:
        print(c, certainty_counts[c])
    # for t in unique_tokens:
    #     print(t)
    return unique_tokens

def destinationCollectionTypes(filename):
    f = open(filename, 'r')
    tracker_links = []
    non_tracker_links = []
    links = []
    trackers, _ = fqdnTrackers(filename)
    broken = set([])
    unique_tokens = []
    for line in f:
        result = json.loads(line)  
        if result['token'] in unique_tokens:
            continue
        unique_tokens.append(result['token'])
        src_context = getSld(result['urls_in_full_redirect_chain'][0])
        dst_context = getSld(result['urls_in_full_redirect_chain'][-1])
        middle_contexts = [getSld(url) for url in result['urls_in_full_redirect_chain'][1:-1]]
        token_contexts = result['contexts']
        src = False
        mid = False
        dst = False
        for c in token_contexts:
            if c == src_context:
                src = True
            if c == dst_context:
                dst = True
            if c in middle_contexts:
                mid = True
        link = ''
        if src and mid and not dst:
            link = 'Originator to Redirector'
        elif mid and dst and not src:
            link = 'Redirector to Destination'
        elif mid and dst and src:
            link = 'Originator to Redirector to Destination'
        elif src and dst and not mid and len(middle_contexts) == 0:
            link = 'Originator to Destination'
        elif mid and not src and not dst:
            link = 'Redirector to Redirector'
        else:
            # print(result['redirect_chain_id'])
            # print('\tsrc:', src, 'mid:', mid, 'dst:', dst)
            # print('\t', src_context, dst_context, middle_contexts, token_contexts)
            broken.add(result['seeder_domain'])
        has_tracker = False
        mids = [getDomain(url) for url in result['urls_in_full_redirect_chain'][1:-1]]
        for m in mids:
            if m in trackers:
                has_tracker = True
        if has_tracker:
            tracker_links.append(link)
        else:
            non_tracker_links.append(link)
        links.append(link)

    num_types = {}
    for t in links:
        if t not in num_types:
            num_types[t] = 0
        num_types[t] += 1

    num_tracker_types = {}
    for t in tracker_links:
        if t not in num_tracker_types:
            num_tracker_types[t] = 0
        num_tracker_types[t] += 1
    num_non_tracker_types = {}
    for t in non_tracker_links:
        if t not in num_non_tracker_types:
            num_non_tracker_types[t] = 0
        num_non_tracker_types[t] += 1

    collection_types = list(num_types.keys())
    collection_numbers = [num_types[name] for name in collection_types]
    sorted_pairs = sorted(zip(collection_numbers, collection_types))
    collection_numbers, collection_types = [list(t) for t in zip(*sorted_pairs)]

    fig, ax = plt.subplots(figsize=(6.5,4))
    y_pos = np.arange(len(collection_types))
    ax.barh(y_pos, collection_numbers, align='center', label='No dedicated smuggler in path', edgecolor = "black")
    ax.barh(y_pos, [num_tracker_types[name] if name in num_tracker_types else 0 for name in collection_types], align='center', label='Dedicated smuggler in path', edgecolor = "black")
    ax.set_yticks(y_pos, labels=collection_types)
    ax.set_xlabel('Number of User Identifiers')
    ax.set_ylabel('Portion of Navigation Path')
    ax.legend(loc='lower right')

    plt.tight_layout()
    plt.savefig('analysis/figs/collection_types.pdf')
    plt.savefig('analysis/figs/collection_types.png')
    plt.show()
    return broken

def fqdnTrackers(filename):
    f = open(filename, 'r')
    srcs_per_fqdn = {}
    dsts_per_fqdn = {}
    fqdn_srcs_and_dsts = set([])
    all_mids = set([])
    for line in f:
        r = json.loads(line)
        mids = r['urls_in_full_redirect_chain'][1:-1]
        src = getDomain(r['urls_in_full_redirect_chain'][0])
        dst = getDomain(r['urls_in_full_redirect_chain'][-1])
        fqdn_srcs_and_dsts.add(src)
        fqdn_srcs_and_dsts.add(dst)
        for m in mids:
            fqdn = getDomain(m)
            all_mids.add(fqdn)
            if fqdn not in srcs_per_fqdn:
                srcs_per_fqdn[fqdn] = set([])
                dsts_per_fqdn[fqdn] = set([])
            srcs_per_fqdn[fqdn].add(getSld(src))
            dsts_per_fqdn[fqdn].add(getSld(dst))
    f.close()

    trackers = set([])
    non_user_facing = set([])
    non_trackers = set([])
    for fqdn in srcs_per_fqdn:
        if fqdn in fqdn_srcs_and_dsts:
            non_user_facing.add(fqdn)
            continue
        if len(srcs_per_fqdn[fqdn]) > 1 and len(dsts_per_fqdn[fqdn]) > 1:
            trackers.add(fqdn)
    for m in all_mids:
        if m not in trackers:
            non_trackers.add(m)
    # for t in trackers:
    #     print(t)
    # print('\nNon-user-facing:')
    # for t in non_trackers:
    #     print(t)
    return trackers, non_trackers

def uniqueRedirectChains(filename):
    chains = {}
    f = open(filename, 'r')
    for line in f:
        r = json.loads(line)
        seed = r['seeder_domain']
        if seed not in chains:
            chains[seed] = set([])
        chain = '_'.join([getDomain(url) for url in r['urls_in_full_redirect_chain']])
        chains[seed].add(chain)
    f.close()
    return chains

def tableOfUidTrackers(filename):
    trackers, non_trackers = fqdnTrackers(filename)
    chains = uniqueRedirectChains(filename)
    unique_chains = set([])
    # Go through and count how many times we saw each tracker.
    tracker_counts = {}
    non_tracker_counts = {}
    for step in chains:
        for chain in chains[step]:
            unique_chains.add(chain)
            mids = chain.split('_')[1:-1]
            for m in mids:
                if m in trackers:
                    if m not in tracker_counts:
                        tracker_counts[m] = 0
                    tracker_counts[m] += 1
                elif m in non_trackers:
                    if m not in non_tracker_counts:
                        non_tracker_counts[m] = 0
                    non_tracker_counts[m] += 1
                else:
                    print("wtf it's not in either?")
    # Get percents
    tracker_percents = {}
    non_tracker_percents = {}
    for chain in unique_chains:
        mids = chain.split('_')[1:-1]
        for m in mids:
            if m in trackers:
                if m not in tracker_percents:
                    tracker_percents[m] = 0
                tracker_percents[m] += 1
            elif m in non_trackers:
                if m not in non_tracker_percents:
                    non_tracker_percents[m] = 0
                non_tracker_percents[m] += 1

    for t in tracker_counts:
        print(t, tracker_percents[t], tracker_percents[t]/len(unique_chains)*100)
    print('\nNon-trackers:')
    for t in non_tracker_counts:
        print(t+'*', non_tracker_percents[t], non_tracker_percents[t]/len(unique_chains)*100)


def lengthsOfRedirectChains(filename):
    tracker_lengths = []
    non_tracker_lengths = []
    chains_per_step = uniqueRedirectChains(filename)
    trackers, _ = fqdnTrackers(filename)
    for step in chains_per_step:
        for chain_str in chains_per_step[step]:
            chain = chain_str.split('_')
            mids = chain[1:-1]
            tracker = False
            for m in mids:
                if m in trackers:
                    tracker = True
            if tracker:
                tracker_lengths.append(len(chain))
            else:
                non_tracker_lengths.append(len(chain))

    lengths = range(0,15) # I already know they range in here
    tracker_bars = {}
    non_tracker_bars = {}
    for l in lengths:
        tracker_bars[l] = 0
        non_tracker_bars[l] = 0
    for l in tracker_lengths:
        tracker_bars[l-2] += 1
    for l in non_tracker_lengths:
        non_tracker_bars[l-2] += 1

    print(tracker_bars)

    fig, ax = plt.subplots(figsize=(5,4))
    ax.bar(lengths, [tracker_bars[l] + non_tracker_bars[l] for l in lengths], label='No dedicated smuggler involved', edgecolor = "black")
    ax.bar(lengths, [tracker_bars[l] for l in lengths], label='Dedicated smuggler involved', edgecolor = "black")
    ax.set_xlabel('Number of redirectors in navigation path')
    ax.set_ylabel('Number of unique navigation paths')
    ax.set_xticks(lengths)
    ax.legend()
    # ax.set_xscale('log')

    plt.tight_layout()
    plt.savefig('analysis/figs/chain_lengths.pdf')
    plt.savefig('analysis/figs/chain_lengths.png')
    plt.show()

def sortBars(value_dict):
    names = list(value_dict.keys())
    numbers = [value_dict[name] for name in names]
    sorted_pairs = sorted(zip(numbers, names))
    numbers, names = [list(t) for t in zip(*sorted_pairs)]
    return numbers, names

def getSld(url):
    return get_sld(url.replace('https://', '').replace('http://', '').split('/')[0].split('?')[0].rstrip('/'))

def navTrackerDomains(filename):
    f = open(filename)
    src_domains = {}
    dst_domains = {}
    mid_domains = {}
    dst_other_domains = {}
    for line in f:
        result = json.loads(line)
        urls = result['urls_in_full_redirect_chain']
        src = getSld(urls[0])
        if src not in src_domains:
            src_domains[src] = 0
        src_domains[src] += 1

        dst = getSld(urls[-1])
        if dst not in dst_domains:
            dst_domains[dst] = 0
        dst_domains[dst] += 1

        if len(urls) > 2:
            mids = urls[1:-1]
            for m in mids:
                mid = getSld(m)
                if mid not in mid_domains:
                    mid_domains[mid] = 0
                mid_domains[mid] += 1

        others = result['destination_web_requests']
        if urls[-1] in result['destination_web_requests']:
            others.remove(urls[-1])
        for o in others:
            other = getSld(o)
            if other not in dst_other_domains:
                dst_other_domains[other] = 0
            dst_other_domains[other] += 1

    src_data, src_names = sortBars(src_domains)
    dst_data, dst_names = sortBars(dst_domains)
    mid_data, mid_names = sortBars(mid_domains)
    other_data, other_names = sortBars(dst_other_domains)
    n = 10

    fig, (ax1, ax2, ax3, ax4) = plt.subplots(1,4, figsize=(12,4))
    ax1.bar(src_names[-1*n:], src_data[-1*n:])
    ax1.set_title('Source')
    ax2.bar(mid_names[-1*n:], mid_data[-1*n:])
    ax2.set_title('Middle')
    ax3.bar(dst_names[-1*n:], dst_data[-1*n:])
    ax3.set_title('Destination')
    ax4.bar(other_names[-1*n:], other_data[-1*n:])
    ax4.set_title('Other destination requests')
    ax1.tick_params(labelrotation=90)
    ax2.tick_params(labelrotation=90)
    ax3.tick_params(labelrotation=90)
    ax4.tick_params(labelrotation=90)

    plt.tight_layout()
    plt.savefig('analysis/figs/nav_trackers.png')
    plt.savefig('analysis/figs/nav_trackers.pdf')
    plt.show()

def amIMissingStuff():
    f = open('results.json', 'r')
    results = []
    for line in f:
        result = json.loads(line) 
        if result['destination_collection_type'] == []:
            continue
        results.append(result['token']+'_'+result['redirect_chain_id'])
    f.close()
    tmp_results2 = []
    f = open('tmp_results2.json', 'r')
    for line in f:
        result = json.loads(line) 
        tmp_results2.append(result['token']+'_'+result['redirect_chain_id'])
    for r in results:
        if r not in tmp_results2:
            print(r)

def cleanJsonFile():
    broken = destinationCollectionTypes('clean_results.json')
    f = open('clean_tokens_2-24.txt', 'r')
    clean_tokens = []
    for line in f:
        clean_tokens.append(line.rstrip())
    f.close()

    f = open('dirty_all_results_2-24.json', 'r')
    results = []
    for line in f:
        result = json.loads(line)
        if result['token'] not in clean_tokens:
            continue
        if "undefined" in result["urls_in_full_redirect_chain"]:
            print(result["redirect_chain_id"])
            continue
        if result['seeder_domain'] in broken:
            continue
        results.append(result)
    f.close()
    f = open('clean_results.json', 'w')
    for r in results:
        json_results = json.dumps(r)
        f.write(json_results+'\n')
    f.close()

def getDomain(url):
    return url.replace('https://', '').replace('http://', '').split('/')[0].split('?')[0].rstrip('/')

def middleDomainsWithoutUids():
    f = open('all_bounce_tracking_without_uids.csv', 'r')
    reader = csv.reader(f, quotechar='`')
    all_middle_domains = {}
    src_domains = set([])
    dst_domains = set([])
    rows = []
    for row in reader:
        if len(row) < 3:
            print('ERROR: len(row) < 3')
        rows.append(row)
        middle_domains = row[1:-1]
        next_domains = {}
        for i, domain in enumerate(middle_domains):
            next_domains[getDomain(domain)] = getDomain(row[i+2])
        pre_domains = [getDomain(url) for url in middle_domains]
        domains = set([])
        src_domain = getDomain(row[0])
        dst_domain = getDomain(row[-1])
        src_domains.add(src_domain)
        dst_domains.add(dst_domain)
        for c in pre_domains:
            if c not in src_domains and c not in dst_domains:
                domains.add(c)
        for c in domains:
            if c not in all_middle_domains:
                all_middle_domains[c] = {'srcs': set([]), 'dsts': set([])}
            all_middle_domains[c]['srcs'].add(src_domain)
            all_middle_domains[c]['dsts'].add(next_domains[c])
    bounce_trackers = set([])
    for c in all_middle_domains:
        # if c == 'forms.gle':
        #     print('forms.gle:', all_middle_domains[c]['srcs'], all_middle_domains[c]['dsts'])
        if len(all_middle_domains[c]['srcs']) > 1 and len(all_middle_domains[c]['dsts']) > 1:
                bounce_trackers.add(c)
            # elif len(middle_contexts[c]['srcs']) > 1:
            #     print(c, '\t\tmultiple sources')
            # elif len(middle_contexts[c]['dsts']) > 1:
            #     print(c, '\t\tmultiple dests')
    # Go through and count how many times we saw each bounce tracker.
    bounce_track_chains = {}
    for row in rows:
        middle_domains = row[1:-1]
        bounce_tracker = ''
        for d in middle_domains:
            if getDomain(d) in bounce_trackers:
                bounce_tracker += getDomain(d)+'_'
        if bounce_tracker == '':
            continue
        if bounce_tracker not in bounce_track_chains:
            bounce_track_chains[bounce_tracker] = 0
        bounce_track_chains[bounce_tracker] += 1
        
    for b in bounce_track_chains:
        print(b, bounce_track_chains[b])
    print('\n', len(rows), 'total chains')

def lessNavTrackingOnChrome(filename):
    f = open(filename, 'r')
    chains_by_seeder = {}
    only_chrome = 0
    both = 0
    only_safari = 0
    s1 = 0
    s2 = 0
    for line in f:
        result = json.loads(line)
        seeder = result['seeder_domain']
        if seeder not in chains_by_seeder:
            chains_by_seeder[seeder] = []
        chains_by_seeder[seeder].append(result)
    for seeder in chains_by_seeder:
        crawlers_per_unique_chains = {}
        for result in chains_by_seeder[seeder]:
            unique_chain = '_'.join([getDomain(url) for url in result['urls_in_full_redirect_chain']])
            if unique_chain not in crawlers_per_unique_chains:
                crawlers_per_unique_chains[unique_chain] = set([])
            crawlers_per_unique_chains[unique_chain].add(result['crawler'])
        for unique_chain in crawlers_per_unique_chains:
            crawlers = crawlers_per_unique_chains[unique_chain]
            if 'chromeProfile' in crawlers and ('safariProfile1' in crawlers or 'safariProfile2' in crawlers):
                both += 1
            elif 'chromeProfile' in crawlers:
                only_chrome += 1
            elif ('safariProfile1' in crawlers or 'safariProfile2' in crawlers):
                only_safari += 1
                if 'safariProfile1' in crawlers:
                    s1 += 1
                else:
                    s2 += 1
    print('Only chrome:', only_chrome, 'only Safari:', only_safari, 'both:', both, 's1', s1, 's2:', s2)

            

def contextsDontMatchUrls(filename):
    f = open(filename, 'r')
    seeders = set([])
    for line in f:
        result = json.loads(line)
        contexts = set([])
        if "undefined" in result["urls_in_full_redirect_chain"]:
            print(result["redirect_chain_id"])
            continue
        for url in result['urls_in_tokens_own_redirects']:
            contexts.add(getSld(url))
        for context in result['storage_contexts']:
            contexts.add(context)
        if contexts != set(result['contexts']):
            seeders.add(result['seeder_domain'])
            print(result['redirect_chain_id'] + '\t'+result['crawler'], contexts, result['contexts'])
    # for s in seeders:
    #         print(s)

def missing():
    f = open('tmp_results2.json')
    new_results = set([])
    for line in f:
        result = json.loads(line)
        # new_results.add(result['token']+'_'+result['seeder_domain']+'_'+result['crawler'])
        new_results.add(result['seeder_domain'])
    f.close()
    f = open('tmp_results.json')
    old_results = set([])
    for line in f:
        result = json.loads(line)
        # old_results.add(result['token']+'_'+result['seeder_domain']+'_'+result['crawler'])
        old_results.add(result['seeder_domain'])
    f.close()
    print('New results:')
    for r in new_results:
        if r not in old_results:
            print(r)
    print('Old results now missing:')
    for r in old_results:
        if r not in new_results:
            print(r)

def isTokenWhereItShouldBe(alleged_crawlers, token, names_in_this_crawler, tokens_per_crawler, this_crawler, names_per_crawler):
    if (this_crawler == 'safariProfile1' or this_crawler == 'safariProfile1Copy') and 'safariProfile1' in alleged_crawlers and 'safariProfile1Copy' in alleged_crawlers:
        if 'safariProfile1' not in tokens_per_crawler:
            print('safariProfile1 missing in tokens_per_crawler. Alleged crawlers:', alleged_crawlers)
            return False
        if 'safariProfile1Copy' not in tokens_per_crawler:
            print('safariProfile1Copy missing in tokens_per_crawler. Alleged crawlers:', alleged_crawlers)
            return False
        # The token value needs to be in both crawlers
        if not (token in tokens_per_crawler['safariProfile1'] and token in tokens_per_crawler['safariProfile1Copy']):
            # print('Tokens in s1:', token in tokens_per_crawler['safariProfile1'], tokens_per_crawler['safariProfile1'])
            # print('Tokens in copy:', token in tokens_per_crawler['safariProfile1Copy'], tokens_per_crawler['safariProfile1Copy'])
            for t in tokens_per_crawler['safariProfile1Copy']:
                print('\t',t == token, token, t)
            print('Same token not found in s1 and s1cpy')
            return False
        elif len(alleged_crawlers) == 2:
            # If these are the only two crawlers, that's it.
            return True

    all_crawlers_but_this_crawler = []
    for c in alleged_crawlers:
        if this_crawler == 'safariProfile1' and c == 'safariProfile1Copy':
            continue
        elif this_crawler == 'safariProfile1Copy' and c == 'safariProfile1':
            continue
        if c != this_crawler:
            all_crawlers_but_this_crawler.append(c)
    
    for crawler in all_crawlers_but_this_crawler:
        name_in_other_crawler = False
        if crawler not in names_per_crawler:
            print('Crawler', crawler, 'missing in names_per_crawler. Alleged crawlers:', alleged_crawlers)
            return False
        for name in names_in_this_crawler:
            if name in names_per_crawler[crawler]:
                name_in_other_crawler = True
        if not name_in_other_crawler:
            print('No name found in', crawler)
            return False
    return True


def isCrawlersPerTokenCorrect(filename):
    f = open(filename, 'r')
    results_per_step = {}
    for line in f:
        result = json.loads(line)
        step = result['seeder_domain']
        if 'iter' not in step:
            step = step+'_iter0'
        if step not in results_per_step:
            results_per_step[step] = []
        results_per_step[step].append(result)

    broken_chains = set([])
    for step in results_per_step:
        results = results_per_step[step]
        tokens_per_crawler = {}
        names_per_crawler = {}
        for r in results:
            crawler = r['crawler']
            token = r['token']
            if crawler not in tokens_per_crawler:
                tokens_per_crawler[crawler] = set([])
            tokens_per_crawler[crawler].add(token)
            if crawler not in names_per_crawler:
                names_per_crawler[crawler] = set([])
            for name in r['names_per_token']:
                names_per_crawler[crawler].add(name)
        for r in results:
            alleged_crawlers = r['crawlers_where_token_name_was_seen']
            token = r['token']
            names_in_this_crawler = r['names_per_token']
            this_crawler = r['crawler']
            if not isTokenWhereItShouldBe(alleged_crawlers, token, names_in_this_crawler, tokens_per_crawler, this_crawler, names_per_crawler):
                # print(r['token'], r['redirect_chain_id'], '\n')
                broken_chains.add(step)
    # for x in broken_chains:
    #     print(x)
    f.close()
    return broken_chains

def fixSeederDomains(filename):
    broken_chains = isCrawlersPerTokenCorrect(filename)
    f = open('all_results.json')
    results = []
    for line in f:
        result = json.loads(line)
        seeder = result['seeder_domain']
        if 'iter' not in seeder:
            seeder = seeder+'_iter0'
        result['seeder_domain'] = seeder
        cid = result['redirect_chain_id']
        if 'iter' not in cid:
            split = cid.split('_')
            cid = split[0]+'_iter0_'+split[1]
        result['redirect_chain_id'] = cid
        if seeder not in broken_chains:
            results.append(result)
    
    outfile = open('dirty_all_results_2-24.json', 'w')
    for r in results:
        json_results = json.dumps(r)
        outfile.write(json_results+'\n')
    outfile.close()
    
def duplicateIds(filename):
    f = open(filename, 'r')
    steps_per_token = {}
    identical_urls = {}
    results = []
    for line in f:
        result = json.loads(line)
        results.append(result)
        token = result['token']
        seed = result['seeder_domain']
        urls = ','.join(result['urls_in_full_redirect_chain'])
        if token not in steps_per_token:
            steps_per_token[token] = set([])
        if urls not in identical_urls:
            identical_urls[urls] = set([])
        steps_per_token[token].add(seed)
        identical_urls[urls].add(seed)
    # for t in steps_per_token:
    #     if len(steps_per_token[t]) > 1:
    #         print(t, steps_per_token[t])
    repeats = {}
    bad_urls = []
    for u in identical_urls:
        if len(identical_urls[u]) > 1:
            seeds = set([])
            for step in identical_urls[u]:
                seeds.add(step.split('_')[0])
            if len(seeds) == 1:
                if len(identical_urls[u]) != 2:
                    continue
                iters = [int(seeder.split('iter')[1]) for seeder in identical_urls[u]]
                if iters[0]-iters[1] != 1 and iters[1]-iters[0] != 1:
                    continue
                if iters[0] < iters[1]:
                    second_step = iters[1]
                else:
                    second_step = iters[0]
                seeder_lst = list(identical_urls[u])
                if str(second_step) in seeder_lst[0]:
                    repeats[u] = seeder_lst[0]
                else:
                    repeats[u] = seeder_lst[1]
                bad_urls.append(u)
                # print(identical_urls[u])

    steps_to_remove = set([])
    for r in results:
        urls = ','.join(r['urls_in_full_redirect_chain'])
        if urls in bad_urls:
            crawlers = len(r['crawlers_where_token_name_was_seen'])
            seeder = r['seeder_domain']
            print(seeder, crawlers)
            print('\tRemoving', repeats[urls])
            steps_to_remove.add(repeats[urls])

    print(steps_to_remove)
    f.close()
    f = open('clean_results_2-27.json', 'r')
    out = open('clean_results.json', 'w')
    for line in f:
        result = json.loads(line)
        if result['seeder_domain'] in steps_to_remove:
            print('Continuing')
            continue
        
        json_results = json.dumps(result)
        out.write(json_results+'\n')
    out.close()

def percentOfNavPathsWithNavTracking(nav_results, all_paths):
    f = open(all_paths, 'r')
    reader = csv.DictReader(f)
    counts = {}
    for row in reader:
        if row['seeder'] not in counts:
            counts[row['seeder']] = {'nav_paths': set([]), 'all_paths': set([])}
        counts[row['seeder']]['all_paths'].add(row['url_chain'])
        # if row['seeder'] == 'couponfollow.com':
        #     print('Adding:\n', row['url_chain'])
    f.close()

    f = open(nav_results, 'r')
    for line in f:
        r = json.loads(line)
        nav_path = '_'.join([url.replace('_','-') for url in r['urls_in_full_redirect_chain']])
        seeder = r['seeder_domain'].split('_')[0]
        if nav_path not in counts[seeder]['all_paths']:
            # Seriously wtf.
            print('ERROR: Nav_path not in all_paths!', nav_path)
        counts[seeder]['nav_paths'].add(nav_path)
    f.close()

    num_nav_paths = 0
    num_all_paths = 0
    for seeder in counts:
        num_nav_paths += len(counts[seeder]['nav_paths'])
        num_all_paths += len(counts[seeder]['all_paths'])
    print('Nav paths:', num_nav_paths, 'All paths:', num_all_paths, 'Percent:', float(num_nav_paths)/float(num_all_paths)*100)

def missingCookieFiles():
    for filename in os.listdir('/data/test_results/safariProfile1/extensionRequests'):
        # print(filename)
        iteration = '_'+filename.split('_')[-2]
        if iteration == '_iter0':
            iteration = ''
        namedate = filename.split('_')[0] + '_' + filename.split('_')[1] + '_' + filename.split('_')[2] + '_' + filename.split('_')[3]
        cookie_file = namedate+'_cookies'+ iteration + '.csv'
        try:
            open('/data/test_results/safariProfile1/cookies/'+cookie_file)
        except:
            print(cookie_file, filename)

def numbersOfChains():
    f = open('clean_results.json', 'r')
    unique_chains = set([])
    fqdn_chains = set([])
    sld_srcs = set([])
    sld_dsts = set([])
    for line in f:
        r = json.loads(line)
        mids = r['urls_in_full_redirect_chain'][1:-1]
        # src = get_sld(getDomain(r['urls_in_full_redirect_chain'][0]))
        # dst = get_sld(getDomain(r['urls_in_full_redirect_chain'][-1]))
        src = getDomain(r['urls_in_full_redirect_chain'][0])
        dst = getDomain(r['urls_in_full_redirect_chain'][-1])
        unique_chains.add('|'.join(r['urls_in_full_redirect_chain']))
        sld_srcs.add(src)
        sld_dsts.add(dst)
        fqdn_chain = []
        for url in r['urls_in_full_redirect_chain']:
            fqdn_chain.append(getDomain(url))
        fqdn_chains.add('|'.join(fqdn_chain))

    print('unique chains', len(unique_chains), 'fqdn chains', len(fqdn_chains))
    print('srcs', len(sld_srcs), 'dsts', len(sld_dsts))
    return sld_srcs, sld_dsts

# Alisha's Disconnect comparison code

def transform_entity_list(entity_list):
    # Given original entity list, map urls to entities instead of vice versa
    new_entity_list = {}
    for org in entity_list["entities"]:
        urls = entity_list["entities"][org]["properties"] + \
            entity_list["entities"][org]["resources"]
        for url in urls:
            new_entity_list[url] = org
    return new_entity_list

def get_disconnect_entity_list():
    # Import Disconnect entity list
    url = requests.get(
        "https://raw.githubusercontent.com/mozilla-services/shavar-prod-lists/master/disconnect-entitylist.json")
    return json.loads(url.text)

# Adds our manual updates -- if you want disconnect only, just use get_disconnect_entity_list()
def create_entity_list():
    entity_list = transform_entity_list(get_disconnect_entity_list())
    additional_entities = pd.read_csv("analysis/additional_entities.csv", dtype={
        "url": "string", "entity": "string"})
    entity_list.update(additional_entities.set_index(
        "url").to_dict()["entity"])
    return entity_list

# entity_list = transform_entity_list(get_disconnect_entity_list())
entity_list = create_entity_list()

def get_entity(url):
    sld = getSld(url)

    # Keep stripping subdomains and checking if its in the entity list
    while sld.find(".") >= 0:
        if sld in entity_list:
            return entity_list[sld]

        # Strip subdomain
        sld = sld[(sld.find(".")+1):]

    print("Unable to find entity for " + getSld(url))
    return getSld(url)

def origsAndDestsInDisconnect():
    srcs, dsts = numbersOfChains()
    in_disconnect = set([])
    slds = set([])
    for src in srcs:
        slds.add(get_sld(src))
        if get_entity(src):
            in_disconnect.add(get_sld(src))
    for dst in dsts:
        slds.add(get_sld(dst))
        if get_entity(dst):
            in_disconnect.add(get_sld(dst))

    print('Srcs+dsts in disconnect:', len(in_disconnect), 'total:', len(slds))

##########################################################
### Begin Alisha's code for the origs and dests owners fig
##########################################################

def numAdditionalEntitySlds():
    slds = set([])
    with open('analysis/additional_entities.csv') as f:
        reader = csv.DictReader(f, quotechar='"')
        for row in reader:
            slds.add(get_sld(row['url']))
    print(len(slds))

def websiteFreqs():
    url_freqs = {}
    for x in range(1, 13):
        f = open(f"stats/brave{x}_stats.csv")
        next(f)  # skip header row
        for line in f:
            sep = line.rindex(",")
            sld = getSld(line[:sep])
            freq = int(line[sep+1:])
            if sld not in url_freqs:
                url_freqs[sld] = 0
            url_freqs[sld] += freq
    return url_freqs

def urlsToDomains(urls):
    # Convert urls_in_full_redirect_chain to domains
    domains = []
    for url in urls:
        domains.append(getDomain(url))
    return domains

def navTrackerEntitiesNormalized(filename):
    f = open(filename)
    src_entities = {}
    dst_entities = {}
    # sld_freqs = entityFreqs()
    visited = []

    for line in f:
        result = json.loads(line)
        urls = result['urls_in_full_redirect_chain']

        # Only check unique (seeder_domain, list of domains) pairs
        # id = (result["seeder_domain"], urlsToDomains(urls))
        id = urlsToDomains(urls)
        if id in visited:
            continue
        visited.append(id)

        src = get_entity(getSld(urls[0]))
        if src not in src_entities:
            src_entities[src] = 0
        src_entities[src] += 1

        dst = get_entity(getSld(urls[-1]))
        if dst not in dst_entities:
            dst_entities[dst] = 0
        dst_entities[dst] += 1


    src_data, src_names = sortBars(src_entities)
    dst_data, dst_names = sortBars(dst_entities)
    n = 19

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    # Source sites
    ax1.barh(src_names[-1*n:], src_data[-1*n:])
    ax1.set_title('Originators')
    ax1.set_xlabel("Number of Appearances")
    ax1.set_ylabel("Originator Organization")
    ax1.set_xticks(range(0, 22, 2))

    # Destination sites
    ax2.barh(dst_names[-1*n:], dst_data[-1*n:])
    ax2.set_title("Destinations")
    ax2.set_xlabel("Number of Appearances")
    ax2.set_ylabel("Destination Organization")
    ax2.set_xticks(range(0, 22, 2))

    plt.tight_layout()
    plt.savefig('analysis/figs/orig_and_dest_entities.png')
    plt.savefig('analysis/figs/orig_and_dest_entities.pdf')
    plt.show()

#########################################################
### End Alisha's code for the origs and dests owners fig
#########################################################

if __name__ == "__main__":
    f = 'clean_results.json'
    destinationCollectionTypes(f)
    # lengthsOfRedirectChains(f)
    # navTrackerDomains(f)
    # amIMissingStuff()
    # cleanJsonFile()
    # middleDomainsWithoutUids()
    # lessNavTrackingOnChrome(f)
    # contextsDontMatchUrls(f)
    # missing()
    # isCrawlersPerTokenCorrect()
    # fixSeederDomains(f)
    # cleanJsonFile()
    # fqdnTrackers(f)
    # tableOfUidTrackers(f)

    # duplicateIds(f)
    # old_tokens = uidCertaintyLevel('clean_results_2-27.json')
    # new_tokens = uidCertaintyLevel('clean_results.json')
    # for token in old_tokens:
    #     if token not in new_tokens:
    #         print(token)
    # percentOfNavPathsWithNavTracking('results.json', 'url_chains.csv')
    # missingCookieFiles()
    # numbersOfChains()
    # dedicated_smugglers, multi_purpose_smugglers = fqdnTrackers(f)
    # print(len(dedicated_smugglers), len(multi_purpose_smugglers), len(set(dedicated_smugglers)), len(set(multi_purpose_smugglers)))

    # origsAndDestsInDisconnect()
    # numAdditionalEntitySlds()

    # navTrackerEntitiesNormalized(f)
