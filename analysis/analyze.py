import csv
import os
import json
import re
import dateutil.parser
import mimetypes
import calendar
import urllib.parse as urlparse
from enum import Enum
from json_flatten import flatten
import validators
from publicsuffix2 import get_sld
from datetime import datetime, timedelta
from http.cookies import SimpleCookie, CookieError

class EventType(Enum):
    COOKIE_READ = 1
    REQUEST = 2
    SET_COOKIE_REQUESTED = 3
    LOCAL_STORAGE_READ = 4

def getSld(url):
    return get_sld(url.replace('https://', '').replace('http://', '').split('/')[0].split('?')[0].rstrip('/'))

class Event:
    def get1pContext(self):
        # For redirects, we can't trust the event.top_level_frame_domain_sld.
        # If the request is for a document and made by the top level frame, the event.domain_sld is the real top level frame SLD.
        if self.resource_type == 'document' and self.frame_id == self.top_level_frame_id:
            return self.domain_sld
        else:
            # We can trust this value for cookies and local storage. 
            return self.top_level_frame_domain_sld

    def __init__(self, event_type, value, name, domain, ts, seeder_domain, frame_domain, frame_id, frame_tree='',top_level_frame_id=0, top_level_frame_domain='', redirect_chain_id=-1, resource_type='', query_id=-1, previous_top_level_url='', url=''):
        self.event_type = event_type
        self.value = value
        self.name = name
        self.domain = domain
        self.ts = ts
        self.seeder_domain = seeder_domain
        self.frame_domain = frame_domain
        self.frame_id = int(frame_id)
        self.frame_domain_sld = getSld(frame_domain)
        self.domain_sld = getSld(domain)

        if event_type == EventType.COOKIE_READ or event_type == EventType.LOCAL_STORAGE_READ:
            self.frame_tree = str(frame_id)
            self.top_level_frame_id = frame_id
            self.top_level_frame_domain = domain
            self.top_level_frame_domain_sld = self.frame_domain_sld
        else:
            self.frame_tree = frame_tree
            self.frame_id = int(frame_id)
            self.top_level_frame_id = int(top_level_frame_id)
            self.top_level_frame_domain = top_level_frame_domain
            self.top_level_frame_domain_sld = getSld(top_level_frame_domain)
        
        self.redirect_chain_id = redirect_chain_id
        self.resource_type = resource_type
        self.query_id = query_id
        self.top_level_frame_domain_sld = self.get1pContext()
        self.previous_top_level_url = previous_top_level_url
        self.url = url


class EvasionDetector:
    # folder = '/data/safari_results/'
    # folder = '/data/redo_results/redone_with_clean_profile/'

    def cookieAlreadyRecorded(self, events, cookie_name, cookie_value, cookie_domain):
        for event in events:
            is_cookie = event.event_type == EventType.COOKIE_READ or event.event_type == EventType.SET_COOKIE_REQUESTED
            if is_cookie and event.name == cookie_name and event.value == cookie_value and event.domain == cookie_domain:
                return True
        return False

    def maybeSplitJson(self, json_str):
        tuples = []
        if re.match('[0-9]+', json_str):
            return tuples
        try:
            parsed_json = json.loads(json_str)
        except json.decoder.JSONDecodeError:
            return tuples
        flat_json = flatten(parsed_json)
        kv_pairs = {}
        for key in flat_json:
            try:
                innermost_key = key.split('.')[-1]
            except AttributeError:
                innermost_key = str(key)
            if innermost_key not in kv_pairs:
                kv_pairs[innermost_key] = set([])
            kv_pairs[innermost_key].add(flat_json[key])
        
        for key in kv_pairs:
            for value in kv_pairs[key]:
                tuples.append((key, value))
        return tuples
        
    def maybeSplitQueryParams(self, param_str):
        tuples = []
        parsed_params = urlparse.parse_qs(param_str)
        if not parsed_params:
            # No query parameters
            return tuples

        for name in parsed_params:
            for value in parsed_params[name]:
                tuples.append((name, value))
        return tuples

    def cookiesFromString(self, string, top_level_frame_domain):
        cookies = []
        for cookie_string in string.split('|'):
            cookie = SimpleCookie()
            try:
                cookie.load(cookie_string)
            except CookieError as err:
                print('Cookie Error:', err)
            for c in cookie:
                if 'domain' in cookie[c]:
                    requested_domain = cookie[c]['domain']
                    if getSld(requested_domain) != top_level_frame_domain:
                        continue
                cookies.append({'value': cookie[c].value, 'name': cookie[c].key, 'domain': top_level_frame_domain})
                # cookies.append({'value': cookie[c].key, 'name': 'cookie_name_for_value_'+cookie[c].value, 'domain': top_level_frame_domain})
        return cookies

    def willInfinitelyRecurse(self, value):
        # If the value is a number, maybeSplitJson will turn it into {'$float': <value>} infinitely.
        # So if it's a number, don't try to jsonify it.
        # Same goes for '{}': you'll get ('$empty', '{}')
        infinite = False
        try:
            float(value)
            infinite = True
        except:
            if value == '{}' or value == '[]':
                infinite = True
        return infinite
    
    def maybeSplitValue(self, value, accumulator):
        if not self.willInfinitelyRecurse(value):
            json_split = self.maybeSplitJson(value)
        else:
            json_split = []
        
        query_split = self.maybeSplitQueryParams(value)
        split = json_split + query_split
        if split == []:
            return []
        accumulator += split
        for (_, val) in split:
            new_split = self.maybeSplitValue(val, accumulator)
            for (new_name, new_val) in new_split:
                if (new_name, new_val) not in accumulator:
                    accumulator.append((new_name, new_val))
        # Recursion over 
        return list(set(accumulator))

    def collectCookies(self, cookie_file):
        events = []
        # Collect all cookie values from cookie file
        seeder_domain = self.getSeederDomainFromFileName(cookie_file)
        f = open(cookie_file, 'r')
        reader = csv.DictReader(f, quotechar='`')
        for row in reader:
            domain = getSld(row['domain'])
            try:
                s = float(row['ts'])/1000
                ts = datetime.fromtimestamp(s)
            except:
                if row['ts'] == 'ts':
                    # This means the results-writing duplication bug happened, so stop analyzing here.
                    break
            maybe_split = []
            self.maybeSplitValue(row['value'], maybe_split)
            if not maybe_split:
                if not self.cookieAlreadyRecorded(events, row['name'], row['value'], domain):
                    # Frame domain is the same as the domain for cookies
                    cookie_event = Event(EventType.COOKIE_READ, row['value'], row['name'], domain, ts, seeder_domain, domain, 0, previous_top_level_url=domain)
                    events.append(cookie_event)
            else:
                for (key, value) in maybe_split:
                    if not self.cookieAlreadyRecorded(events, key, value, domain):
                        # Frame domain is the same as the domain for cookies
                        cookie_event = Event(EventType.COOKIE_READ, value, key, domain, ts, seeder_domain, domain, 0, previous_top_level_url=domain)
                        events.append(cookie_event)
        f.close()
        return events
    
    def collectRedirectChains(self, events):
        redirect_chains = {}
        redirect_chain_event_idxs = {}
        current_chain = []
        current_event_idxs = []
        current_chain_id = 0

        if len(events) == 0:
            return []

        last_ts = events[0].ts
        for event_idx, event in enumerate(events):
            # We only care about redirect chains that happened in the top level document.
            if event.frame_id != event.top_level_frame_id:
                continue
            
            if event.resource_type == 'document': 
                # Is this event part of a new chain?
                if event.ts - last_ts > timedelta(seconds=1) or len(current_chain) == 0 or event.frame_id != current_chain[-1].frame_id:
                    if current_chain != []:
                        redirect_chains[current_chain_id] = current_chain
                    current_chain = [event]
                    current_event_idxs = [event_idx]
                    current_chain_id += 1
                else:
                    current_chain.append(event)
                    current_event_idxs.append(event_idx)
                last_ts = event.ts
            if current_chain != []:
                redirect_chains[current_chain_id] = current_chain
                redirect_chain_event_idxs[current_chain_id] = current_event_idxs

        # Remove chains that didn't cause a 1p context change
        redirect_chains_to_return = {}
        previous_events = {}
        for chain_id in redirect_chains:
            # Did this chain cause a change in 1p context?
            first_event_idx = redirect_chain_event_idxs[chain_id][0]
            if first_event_idx == 0:
                # This was the document request that loaded the source page. By definition, it wasn't doing any nav racking.
                continue
            
            # Find the last web request and figure out what the 1p context was before the document request
            previous_request_event = events[first_event_idx-1]
            i = 2
            while previous_request_event.event_type != EventType.REQUEST:
                previous_request_event = events[first_event_idx-i]
                i+=1
            
            previous_events[chain_id] = previous_request_event
            found_different_context = False
            for redirect_event in redirect_chains[chain_id]:
                if previous_request_event.get1pContext() != redirect_event.get1pContext():
                    found_different_context = True
            
            if found_different_context:
                redirect_chains_to_return[chain_id] = redirect_chains[chain_id]

        for cid in redirect_chains:
            if cid not in previous_events:
                continue
            print(cid)
            print('\t', previous_events[cid].query_id, previous_events[cid].get1pContext(), '(previous request)')
            for event in redirect_chains[cid]:
                print('\t', event.query_id, event.get1pContext())
        return redirect_chains_to_return

    def addRedirectChainsToUrlChains(self, redirect_chains, crawl_file):
        seeder_plus_iteration = self.getSeederDomainFromFileName(crawl_file)
        seeder = seeder_plus_iteration.split('_')[0]
        for cid in redirect_chains:
            chain = redirect_chains[cid]
            if seeder not in url_chains:
                url_chains[seeder] = set([])
            
            previous_url = chain[0].previous_top_level_url
            url_chain = [previous_url]
            for event in chain:
                if event.url == previous_url:
                    continue
                previous_url = event.url
                url_chain.append(event.url)

            url_chain_str = '_'.join([url.replace('_','-') for url in url_chain])
            print('URL chain:', url_chain_str)
            url_chains[seeder].add(url_chain_str)

    def collectQueryParamsAndSetCookies(self, crawl_file):
        events = []
        seeder_domain = self.getSeederDomainFromFileName(crawl_file)
        try:
            f = open(crawl_file, 'r')
        except FileNotFoundError as err:
            print('Could not open '+crawl_file)
            return events
        
        reader = csv.DictReader(f, quotechar='`')
        query_id = 0
        for row in reader:
            query_id += 1
            if row['type'] == 'navigation':
                continue
            if row['url'] != '':
                domain = getSld(row['url'])
            else:
                domain = getSld(row['expectedUrl'])
            
            try:
                s = float(row['time'])/1000000.0
                ts = datetime.fromtimestamp(s)
            except ValueError as err:
                if row['time'] == 'time':
                    # The crawler had to redo the step. Discard the previous results and use the results from here on out.
                    # This is only a temporary solution: need to do this to storage and cookies too.
                    events = []
                    continue
                print('Error creating timestamp:', err)

            # Update map of visited sites
            if row['resourceType'] == 'document' or row['resourceType'] == 'sub_frame':
                # Update map of top level sites visited
                if row['resourceType'] == 'document':
                    url_without_params = row['url'].split('?')[0]
                    if url_without_params not in tl_sites_visited:
                        tl_sites_visited[url_without_params] = 0
                    tl_sites_visited[url_without_params] += 1

            try:
                top_level_frame_id = int(row['frameTree'].split('-')[-1])
                frame_id = int(row['frameId'])
            except ValueError as err:
                print("Error in crawl events collector:", crawl_file, err)
                continue

            # Request event with query params
            unique_params = []
            parsed_url = urlparse.urlparse(row['url'])
            parsed_params = urlparse.parse_qs(parsed_url.query)
            for param_name in parsed_params:
                for param_val in parsed_params[param_name]:
                    maybe_split = []
                    self.maybeSplitValue(param_val, maybe_split)
                    if not maybe_split:
                        maybe_split = [(param_name, param_val)]
                    unique_params += maybe_split
            for (key, value) in list(set(unique_params)):
                request_event = Event(EventType.REQUEST, value, key, domain,
                    ts, seeder_domain, row['frameDomain'], frame_id, frame_tree = row['frameTree'], 
                    top_level_frame_domain=row['topLevelFrameDomain'], 
                    top_level_frame_id=top_level_frame_id, 
                    resource_type=row['resourceType'], query_id=query_id,
                    url = row['url'])
                events.append(request_event)
                    
        f.close()
        return events

    def setPreviousUrls(self, request_events):
        if len(request_events) == 0:
            return request_events
        previous_top_level_url = request_events[0].top_level_frame_domain
        current_top_level_url = request_events[0].top_level_frame_domain
        for event in request_events:
            if event.resource_type == 'document':
                previous_top_level_url = current_top_level_url
                current_top_level_url = event.top_level_frame_domain
            event.previous_top_level_url = previous_top_level_url
        return request_events

    def getSeederDomainFromFileName(self, filename):
        captures = re.search('_[AP]M_(?P<seeder_domain>.+)_(localStorage|cookies|extensionRequests)(?P<iteration>_iter[0-9]+)?', filename).groupdict()
        if 'seeder_domain' not in captures:
            captures = re.search('_[AP]M_(?P<seeder_domain>.+)(?P<iteration>_iter[0-9]+)?_(localStorage|cookies|extensionRequests)', filename).groupdict()
        seeder_domain = captures['seeder_domain']
        if captures['iteration'] is not None and captures['iteration'] != '_iter0':
            seeder_domain += captures['iteration']
        return seeder_domain

    def collectLocalStorage(self, ls_file):
        events = []
        # /data/test_results/safariProfile1/localStorage/11-18-2021_2:21:52_AM_ricoh.com_localStorage.csv
        # 11-22-2021_17:41:32_PM_instagram.com_localStorage_iter1.csv
        seeder_domain = self.getSeederDomainFromFileName(ls_file)
        try:
            f = open(ls_file, 'r')
        except FileNotFoundError as err:
            return events
        reader = csv.DictReader(f, quotechar='`')
        try:
            for row in reader:
                domain = getSld(row['domain'])
                try:
                    s = float(row['ts'])/1000
                    ts = datetime.fromtimestamp(s)
                except:
                    continue
                maybe_split = []
                self.maybeSplitValue(row['value'], maybe_split)
                if not maybe_split:
                    ls_event = Event(EventType.LOCAL_STORAGE_READ, row['value'], row['key'], domain, ts, seeder_domain, domain, row['frameId'], previous_top_level_url=domain)
                    events.append(ls_event)
                else:
                    for (key, value) in maybe_split:
                        ls_event = Event(EventType.LOCAL_STORAGE_READ, value, key, domain, ts, seeder_domain, domain, row['frameId'], previous_top_level_url=domain)
                        events.append(ls_event)
        except:
            self.errorFiles.append(ls_file)
        f.close()
        return events

    def sortRedirectChain(self, redirect_chain):
        storage_events_by_context = {}
        request_events = []
        for event in redirect_chain:
            if event.event_type == EventType.COOKIE_READ or event.event_type == EventType.LOCAL_STORAGE_READ:
                context = event.get1pContext()
                if context not in storage_events_by_context:
                    storage_events_by_context[context] = []
                storage_events_by_context[context].append(event)
            else:
                request_events.append(event)

        request_events.sort(key=lambda event: event.ts)
        current_context = request_events[0].get1pContext()
        sorted_events = []
        if current_context in storage_events_by_context:
            for storage_event in storage_events_by_context[current_context]:
                sorted_events.append(storage_event)
        for request_event in request_events:
            context = request_event.get1pContext()
            if current_context != context:
                if context in storage_events_by_context:
                    for storage_event in storage_events_by_context[context]:
                        sorted_events.append(storage_event)
                current_context = context
            sorted_events.append(request_event)
        return sorted_events

    def eventsSurroundingChain(self, events, redirect_chain, redirect_chain_id):
        surrounding_events = []
        # Find the context before the click
        first_event_idx = events.index(redirect_chain[0])
        if first_event_idx != 0: # If 0, this was the document request that loaded the source page. No previous context.
            # Find the last web request and figure out what the 1p context was before the document request
            previous_request_event = events[first_event_idx-1]
            i = 2
            while previous_request_event.event_type != EventType.REQUEST and first_event_idx-i >= 0:
                previous_request_event = events[first_event_idx-i]
                i+=1
        else:
            previous_request_event = redirect_chain[0]
        # Add all the events in the context before the click
        first_context = previous_request_event.get1pContext()
        previous_req_idx = events.index(previous_request_event)
        i = previous_req_idx
        while i > 0 and events[i].get1pContext() == first_context and events[i].resource_type != 'document':
            surrounding_events.insert(0, events[i])
            i -= 1
        # Add all the events from the request before the redirect chain to the end of the redirect chain
        for event in events[previous_req_idx+1:events.index(redirect_chain[-1])+1]:
            surrounding_events.append(event)
        # Add all the events in the context of the destination, until the context changes
        final_context = redirect_chain[-1].get1pContext()
        for event in events[events.index(redirect_chain[-1])+1:]:
            if event.get1pContext() != final_context or event.resource_type == 'document':
                break
            surrounding_events.append(event) 
        # And finally, because the timestamps don't quite match up, add all the cookies and local storage from the right contexts.
        contexts = set([e.get1pContext() for e in redirect_chain])
        contexts.add(first_context)
        for e in events:
            if e.event_type == EventType.COOKIE_READ or e.event_type == EventType.LOCAL_STORAGE_READ and e.get1pContext() in contexts:
                surrounding_events.append(e)
        
        # seen = []
        # for e in surrounding_events:
        #     if e.query_id not in seen:
        #         print('\t',e.query_id)
        #         seen.append(e.query_id)
        return self.sortRedirectChain(surrounding_events)

    def collectRepeatedTokensPerChain(self, events, redirect_chain, chain_id):
        surrounding_events = self.eventsSurroundingChain(events, redirect_chain, chain_id)
        contexts_per_token = {}
        for event in surrounding_events:
            token = event.value
            if token not in contexts_per_token:
                contexts_per_token[token] = set([])
            contexts_per_token[token].add(event.get1pContext())
        tokens_in_chain = set([])
        for event in redirect_chain:
            tokens_in_chain.add(event.value)
        repeated_tokens = set([])
        for token in contexts_per_token:
            # A token is only repeated if it was in multiple contexts AND in the document requests.
            if len(contexts_per_token[token]) >= 2 and token in tokens_in_chain:
                repeated_tokens.add(token)
        # print(repeated_tokens)

        # Find all events in surrounding_events that contain these tokens. 
        # Add them to the redirect chain and sort it.
        for event in surrounding_events:
            if event not in redirect_chain and event.value in repeated_tokens:
                redirect_chain.append(event)
        redirect_chain = self.sortRedirectChain(redirect_chain)
        return redirect_chain, repeated_tokens
    
    def oldCollectRepeatedTokens(self, events, redirect_chains):
        # Make a map of all tokens to the 1p contexts they belong to.
        contexts_per_token = {}
        previous_contexts = {}
        for i, event in enumerate(events):
            context = event.get1pContext()
            token = event.value
            if token not in contexts_per_token:
                contexts_per_token[token] = set([])
            contexts_per_token[token].add(context)
            if event.resource_type == 'document':
                previous_contexts[event] = events[i-1].get1pContext()

        repeated_tokens = set([])
        for token in contexts_per_token:
            # print(token, contexts_per_token[token])
            if len(contexts_per_token[token]) > 1:
                repeated_tokens.add(token)

        # Find all redirect chains (right now, just chains of document requests) that include a repeated token,
        # and make a map of tokens to the chains that contain them
        repeated_token_chains = {}
        repeated_tokens_per_chain = {}
        chain_ids_by_token = {}
        for chain_id in redirect_chains:
            chain_contexts = set([])
            for event in redirect_chains[chain_id]:
                chain_contexts.add(event.get1pContext())
            
            for event in redirect_chains[chain_id]:
                if event.value in repeated_tokens:
                    # Make sure the contexts that this token appears in have a document request that connects them that contains the token
                    # print('Contexts per token:', contexts_per_token[token])
                    # print('Chain contexts:', chain_contexts)
                    skip_token = False
                    for context in contexts_per_token[token]:
                        if context not in chain_contexts:
                            skip_token = True
                    if skip_token: # if contexts_per_token[token].issubset(chain_contexts):
                        continue

                    repeated_token_chains[chain_id] = redirect_chains[chain_id]
                    if event.value not in chain_ids_by_token:
                        chain_ids_by_token[event.value] = set([])
                    chain_ids_by_token[event.value].add(chain_id)
                    if chain_id not in repeated_tokens_per_chain:
                        repeated_tokens_per_chain[chain_id] = []
                    repeated_tokens_per_chain[chain_id].append(token)

        for chain_id in repeated_token_chains:
            surrounding_events = self.eventsSurroundingChain(events, repeated_token_chains[chain_id], chain_id)
            # For each chain of document requests that includes a repeated token, add all cookies, local storage events, and non-document requests that also have that token.
            for event in surrounding_events:
                if event.value not in repeated_tokens or event.resource_type == 'document':
                    continue

                ##############################################
                ## NOTE: If the following if clause is triggered, it means there are tokens that passed from one context to another without going through a redirect chain.
                ## This probably means they're things like True, a date, 1, or other values that weren't actually SENT, they're just coincidentally the same. 
                ## However, it MIGHT mean it's a UID token that actually got transferred through another metjod than a query parameter.
                ## Since I expect most of these tokens to be non-UIDs, I'm leaving them out for now.
                ## But if we want to put them back in, remove the following if clause.
                ###############################################
                # if event.value not in chain_ids_by_token:
                #     continue
                if event.value not in repeated_tokens_per_chain[chain_id]:
                    if event.value == '205977932.4.1644933258937':
                        print('Not adding token', repeated_tokens_per_chain[chain_id])
                    continue

                repeated_token_chains[chain_id].append(event)

        # Sort the chains by timestamp now that we've added all the non-document-request events.
        # Except Puppeteer timestamps don't seem to agree well with Chrome extension timestamps, so put the cookies in place based on context instead.
        for chain_id in repeated_token_chains:
            repeated_token_chains[chain_id] = self.sortRedirectChain(repeated_token_chains[chain_id])

        return repeated_token_chains, repeated_tokens
    
    def howTokenIsUsedByDestinations(self, redirect_chain, uid_tokens_in_chain):
        token_contexts = {} # {token: [first_context, second_context,...,nth_context]}
        destination_collection_type = {} #{token: [use1, use2, use3...]}
        dst_web_requests = {} # {token: [all_web_requests in dest context that used the token]}

        for event in redirect_chain:
            if event.value not in uid_tokens_in_chain:
                continue
            token = event.value
            context = event.get1pContext()
            if token not in token_contexts:
                token_contexts[token] = [context]
            if token_contexts[token][-1] != context:
                token_contexts[token].append(context)

        for event in redirect_chain:
            token = event.value
            if token not in uid_tokens_in_chain:
                continue
            if token not in destination_collection_type:
                destination_collection_type[token] = set([])
            if token not in dst_web_requests:
                dst_web_requests[token] = set([])
            # Is this event a src, st, or middle event from the point of view of its token value?
            event_context = event.get1pContext()
            context_idx = token_contexts[token].index(event_context)
            if context_idx == 0:
                # Source context
                continue
            elif context_idx == len(token_contexts[token])-1:
                # Final destination context
                dst = event
                if dst.event_type == EventType.REQUEST or dst.event_type == EventType.SET_COOKIE_REQUESTED:
                    dst_web_requests[token].add(dst.url)
                    if dst.frame_id == dst.top_level_frame_id:
                        if dst.resource_type == 'document':
                            destination_collection_type[token].add('document-resource-request-of-destination-domain')
                        elif dst.domain == dst.top_level_frame_domain_sld:
                            destination_collection_type[token].add('subresource-request-of-destination-domain')
                        else:
                            destination_collection_type[token].add('subresource-request-of-different-domain')
                    else:
                        if dst.resource_type == 'document':
                            destination_collection_type[token].add('iframe-document-resource-request-of-destination-domain')
                        elif dst.domain == dst.top_level_frame_domain_sld:
                            destination_collection_type[token].add('iframe-subresource-request-of-destination-domain')
                        else:
                            destination_collection_type[token].add('iframe-subresource-request-of-different-domain')
                elif dst.event_type == EventType.COOKIE_READ:
                    # If it's a cookie or local storage, it came from the top level frame
                    destination_collection_type[token].add('cookie-under-destination-domain')
                else:
                    destination_collection_type[token].add('local-storage-under-destination-domain')
            else:
                # Middle domain
                if event.event_type == EventType.REQUEST and event.resource_type != 'document':
                    print('ERROR: This event is a middle domain but is not a document request, I thought that was impossible.')
                destination_collection_type[token].add('document_request_of_middle_domain')

        return destination_collection_type, token_contexts, dst_web_requests

    
    def fitIntoTaxonomy(self, redirect_chain, redirect_chain_id, uid_tokens, crawlers_per_token, names_per_token, crawler=''):
        seeder_domain = redirect_chain[0].seeder_domain

        # URLs in redirect chain
        urls_in_redirect_chain = []
        for event in redirect_chain:
            if event.resource_type != 'document' or '-' in event.frame_tree or (len(urls_in_redirect_chain) > 0 and urls_in_redirect_chain[-1] == event.url) or event.url == '':
                continue
            if len(urls_in_redirect_chain) == 0:
                urls_in_redirect_chain.append(event.previous_top_level_url)
            urls_in_redirect_chain.append(event.url)

        # Contexts in which the token appeared as cookie or local storage
        # and source 3p web requests
        storage_contexts = {}
        src_web_requests = {}
        src_context = redirect_chain[0].get1pContext()
        for event in redirect_chain:
            token = event.value
            if token not in storage_contexts:
                storage_contexts[token] = set([])
            if token not in src_web_requests:
                    src_web_requests[token] = set([])
            if event.event_type == EventType.REQUEST and event.get1pContext() == src_context and event.resource_type != 'document':
                src_web_requests[token].add(event.url)
            if event.event_type == EventType.COOKIE_READ or event.event_type == EventType.LOCAL_STORAGE_READ:
                storage_contexts[token].add(event.get1pContext())

        # How is the token used by the destinations and middle domains?
        pre_destination_collection_type, pre_contexts, pre_destination_web_requests = self.howTokenIsUsedByDestinations(redirect_chain, uid_tokens)

        # I don't understand how this is happening, but if we end up with a token here that only has one context and/or has no destination_collection_type, remove it.
        destination_collection_type = {}
        contexts = {}
        destination_web_requests = {}
        for token in pre_destination_collection_type:
            if len(pre_destination_collection_type[token]) == 0 or len(pre_contexts[token]) < 2:
                continue
            destination_collection_type[token] = pre_destination_collection_type[token]
            contexts[token] = pre_contexts[token]
            destination_web_requests[token] = pre_destination_web_requests[token]

        all_results = []
        for token in destination_collection_type:
            # Which URLs are involved in the path of each token? If a token was only passed through part of the redirect chain, these are the URLs it was passed through.
            urls_in_tokens_own_redirects = []
            for context in contexts[token]:
                for url in urls_in_redirect_chain:
                    if getSld(url) == context:
                        urls_in_tokens_own_redirects.append(url)
            results = {
                'token': token,
                'redirect_chain_id': seeder_domain + '_' + str(redirect_chain_id),
                'seeder_domain': seeder_domain,
                'crawler': crawler,
                'crawlers_where_token_name_was_seen': crawlers_per_token[token],
                'transfer_type': 'query_parameter',
                'destination_collection_type': list(destination_collection_type[token]),
                'urls_in_full_redirect_chain': urls_in_redirect_chain,
                'urls_in_tokens_own_redirects': urls_in_tokens_own_redirects, # If a token was only passed through part of the redirect chain, these are the URLs it was passed through.
                'destination_web_requests': list(destination_web_requests[token]), # All web requests on the destination site that included the UID as a query param
                'source_web_requests': list(src_web_requests[token]),
                'contexts': contexts[token],
                'storage_contexts': list(storage_contexts[token]),
                'names_per_token': list(names_per_token[token])
            }
            # csv_lines.append(self.generateLineForCsv(redirect_chain_id, src, dst, results, crawler=crawler))
            all_results.append(results)

        return all_results

    def findRedirectChainsWithoutUids(self, redirect_chains):
        # URLs in redirect chain
        redirect_chains_to_return = {}
        for chain_id in redirect_chains:
            urls_in_redirect_chain = []
            for event in redirect_chains[chain_id]:
                if event.resource_type != 'document' or '-' in event.frame_tree or (len(urls_in_redirect_chain) > 0 and urls_in_redirect_chain[-1] == event.url) or event.url == '':
                    continue
                if len(urls_in_redirect_chain) == 0:
                    urls_in_redirect_chain.append(event.previous_top_level_url)
                urls_in_redirect_chain.append(event.url)
            contexts = set([getSld(url) for url in urls_in_redirect_chain])
            if len(contexts) < 3:
                continue
            redirect_chains_to_return[chain_id] = redirect_chains[chain_id]
        # This isn't enough, I need to know which of these don't have UIDs in them and I won't know that until later.
        return redirect_chains_to_return
            
    
    def reconstructEvents(self, files):
        request_events = self.collectQueryParamsAndSetCookies(files['extensionRequests'])
        # request_events_with_frame_domains = self.setFrameDomains(request_events)
        events = self.setPreviousUrls(request_events)
        events += self.collectCookies(files['cookies'])
        events += self.collectLocalStorage(files['localStorage'])
        
        # Sort events by ts
        events.sort(key=lambda event: event.ts)
        redirect_chains = self.collectRedirectChains(events)
        if (redirect_chains == {}):
            return {}, {}, []
        self.addRedirectChainsToUrlChains(redirect_chains, files['extensionRequests'])
        redirect_chains_maybe_without_uids = self.findRedirectChainsWithoutUids(redirect_chains)
        
        repeated_token_chains = {}
        repeated_tokens = {}
        for chain_id in redirect_chains:
            repeated_token_chain, repeated_tokens_per_chain = self.collectRepeatedTokensPerChain(events, redirect_chains[chain_id], chain_id)
            print(repeated_tokens_per_chain)
            if repeated_token_chain == []:
                continue
            repeated_token_chains[chain_id] = repeated_token_chain
            repeated_tokens[chain_id] = repeated_tokens_per_chain
        return repeated_token_chains, repeated_tokens, redirect_chains_maybe_without_uids
    
    def __init__(self, folder, crawler='not set'):
        #Folders
        self.folder = folder + '/'
        self.cookieFolder = self.folder+'cookies'
        self.crawlEventFolder = self.folder+'extensionRequests'
        self.localStorageFolder = self.folder+'localStorage'
        self.errorFiles = []
        self.crawler = crawler


class TokenClassifier:
    def isDatetime(self, token):
        if len(token) < 10:
            return False

        if isinstance(token, str):
            try:
                dateutil.parser.parse(token, ignoretz=True)
                return True
            except (dateutil.parser.ParserError, OverflowError,  # type: ignore
                    calendar.IllegalMonthError, TypeError):
                return False

        float_token = None
        try:
            float_token = float(token)
        except ValueError:
            return False

        # Otherwise check and see if this looks like a numberic encoding of a
        # timestamp.
        year_start_ts = 1609484400
        year_end_ts = 1641020400
        if float_token > year_start_ts and float_token < year_end_ts:
            return True

        year_start_ts_ms = 1609484400000
        year_end_ts_ms = 1641020400000
        # Next, see if it looks like a millisecond timestamp
        if float_token > year_start_ts_ms and float_token < year_end_ts_ms:
            return True

        # Finally, filter out relative timestamps (like from performance.now).
        if float_token and float_token < 10000000:
            return True

        return False

    def isUserTracker(self):
        if len(self.token) < 8:
            return False
        
        if validators.url(self.token):
            return False

        if self.isDatetime(self.token):
            return False

        # File name?
        (mimetype, _) = mimetypes.guess_type(self.token)
        if mimetype is not None:
            return False

        return True

    def __init__(self, token):
        self.token = token

def crawlersPerToken(uid_tokens, names_per_crawler, redirect_chains_by_crawler):
    tokens_per_name = {}
    for crawler in redirect_chains_by_crawler:
        redirect_chains = redirect_chains_by_crawler[crawler]
        for chain_id in redirect_chains:
            for event in redirect_chains[chain_id]:
                if event.value not in uid_tokens:
                    continue
                if event.name not in tokens_per_name:
                    tokens_per_name[event.name] = set([])
                tokens_per_name[event.name].add(event.value)
    
    
    crawlers_per_token = {} # {token: [crawler1, crawler2,...]}
    names_per_token_per_crawler = {} # {crawler: {token: [name1, name2,...]}}
    for crawler in names_per_crawler:
        names_per_token_per_crawler[crawler] = {}
        for name in names_per_crawler[crawler]:
            if name not in tokens_per_name:
                continue
            for token in tokens_per_name[name]:
                if token not in crawlers_per_token:
                    crawlers_per_token[token] = set([])
                crawlers_per_token[token].add(crawler)
                if token not in names_per_token_per_crawler[crawler]:
                    names_per_token_per_crawler[crawler][token] = set([])
                names_per_token_per_crawler[crawler][token].add(name)
    for token in crawlers_per_token:
        crawlers_per_token[token] = list(crawlers_per_token[token])
    return crawlers_per_token, names_per_token_per_crawler

def removeNonUids(pre_repeated_tokens_by_crawler, pre_repeated_token_names_by_crawler, non_uid_names):
    all_tokens = set([])
    repeated_tokens_by_crawler = {}
    repeated_token_names_by_crawler = {}
    non_uid_tokens = set([])

    for crawler in pre_repeated_token_names_by_crawler:
        for name in pre_repeated_token_names_by_crawler[crawler]:
            if name in non_uid_names:
                for value in pre_repeated_token_names_by_crawler[crawler][name]:
                    non_uid_tokens.add(value)
            else:
                if crawler not in repeated_token_names_by_crawler:
                    repeated_token_names_by_crawler[crawler] = {}
                repeated_token_names_by_crawler[crawler][name] = list(pre_repeated_token_names_by_crawler[crawler][name])[0]
    print('Non-UID values:', non_uid_tokens)
    for crawler in pre_repeated_tokens_by_crawler:
        for token in pre_repeated_tokens_by_crawler[crawler]:
            if token in non_uid_tokens:
                continue
            if crawler not in repeated_tokens_by_crawler:
                repeated_tokens_by_crawler[crawler] = set([])
            repeated_tokens_by_crawler[crawler].add(token)
            all_tokens.add(token)
    return all_tokens, repeated_tokens_by_crawler, repeated_token_names_by_crawler

def getUidTokens(all_tokens, repeated_tokens_by_crawler, repeated_token_names_by_crawler):
    # First, remove all tokens that are the same across any two user profiles, except s1 and s1copy.
    non_identical_tokens = []
    for token in all_tokens:
        crawlers = set([])
        for crawler in repeated_tokens_by_crawler:
            if token in repeated_tokens_by_crawler[crawler]:
                # Condense safariProfile1 and safariProfile1Copy into one, since they use the same profile
                c = crawler
                if c == 'safariProfile1Copy':
                    c = 'safariProfile1'
                crawlers.add(c)

        if len(crawlers) > 1:
            # If a token appears in any two profiles, since s1 and s1copy are condensed, it isn't a UID.
            continue
        non_identical_tokens.append(token)

    # Next, find all tokens that are not the same in safariProfile1 and safariProfile1Copy.
    session_ids = []
    if 'safariProfile1' in repeated_token_names_by_crawler and 'safariProfile1Copy' in repeated_token_names_by_crawler:
        for token_name in repeated_token_names_by_crawler['safariProfile1']:
            # If the same token name shows up in both crawlers, but the token value is different, the token is not a UID, it's probably a session ID or something.
            if token_name in repeated_token_names_by_crawler['safariProfile1Copy'] and repeated_token_names_by_crawler['safariProfile1'][token_name] != repeated_token_names_by_crawler['safariProfile1Copy'][token_name]:
                session_ids.append(repeated_token_names_by_crawler['safariProfile1'][token_name])
                session_ids.append(repeated_token_names_by_crawler['safariProfile1Copy'][token_name])
                if 'safariProfile2' in repeated_token_names_by_crawler and token_name in repeated_token_names_by_crawler['safariProfile2']:
                    session_ids.append(repeated_token_names_by_crawler['safariProfile2'][token_name])
                if 'chromeProfile' in repeated_token_names_by_crawler and token_name in repeated_token_names_by_crawler['chromeProfile']:
                    session_ids.append(repeated_token_names_by_crawler['chromeProfile'][token_name])
    
    # Remove the identical-across-profiles tokens.
    uid_tokens_without_heuristic = []          
    for token in non_identical_tokens:
        if token not in session_ids:
            uid_tokens_without_heuristic.append(token)
   

    # Remove all tokens remaining that don't fit our heuristics for what UIDs look like.
    uid_tokens = []
    for token in uid_tokens_without_heuristic:
        classifier = TokenClassifier(token)
        if not classifier.isUserTracker():
            continue
        uid_tokens.append(token)
                
    return uid_tokens

# This function is used to compare our four-crawler technique to the two-crawler technique used in previous work.
def getUidTokensByTwoCrawlersOnly(all_tokens, repeated_tokens_by_crawler, repeated_token_names_by_crawler):
    different_tokens = set([])
    if 'safariProfile1' not in repeated_tokens_by_crawler or 'safariProfile2' not in repeated_tokens_by_crawler:
        # Fouad et al. discarded tokens that weren't in both crawls, so if no tokens were in a crawl, discard all tokens.
        return []
    
    safari1_tokens = repeated_tokens_by_crawler['safariProfile1']
    safari2_tokens = repeated_tokens_by_crawler['safariProfile2']
    for token in all_tokens:
        # Token needs to be in either safari1 or safari2 but not both (if it's in both it's not a UID)
        if token in safari1_tokens or token in safari2_tokens and not (token in safari1_tokens and token in safari2_tokens):
            different_tokens.add(token)

    return list(different_tokens)

# This function is used to compare our four-crawler technique to the heuristics used in previous work.
def getUidTokensByHeuristicOnly(all_tokens, repeated_tokens_by_crawler, repeated_token_names_by_crawler):
    # Remove all tokens remaining that don't fit our heuristics for what UIDs look like.
    uid_tokens = []
    for token in all_tokens:
        classifier = TokenClassifier(token)
        if not classifier.isUserTracker():
            continue
        uid_tokens.append(token)
    return uid_tokens

def getUidsKoopsWay(all_tokens, repeated_tokens_by_crawler, repeated_token_names_by_crawler):
    # We only need safari1 for this.
    tokens = makeKoopsTokenDict() # {top_level_domain: {name: [values_across_random_walks]}}. If values are the same within a random walk that's fine but make sure to count them as one value.
    uid_tokens = []
    for context in tokens:
        for name in tokens[context]:
            values = tokens[context][name]
            # If any values are the same across random walks, this token is not a UID according to Koop et al.
            if anyValuesAreTheSame(values):
                continue
            similarities = getRatcliffObershelpSimilarities(values) # {value: [similarity to all other values]}
            for value in similarities:
                num_different = sum([1 if x <= 0.66 else 0 for x in similarities[value]])
                if num_different >= len(similarities[value])/2:
                    # This token is a UID by Koop et al.'s definition.
                    uid_tokens.append((name, value))

    return uid_tokens

def getFilesFromCrawl(safari1_cookie_file, cookie_filenames):
    # Example cookie file: 11-18-2021_12:07:32_PM_freenode.net_cookies_iter8.csv 
    prefix = safari1_cookie_file.split('_cookies')[0]  # 11-18-2021_9:55:01_AM_freenode.net
    if 'iter' in safari1_cookie_file.split('_cookies')[1]:
        iteration = safari1_cookie_file.split('_cookies')[1].replace('.csv','')  # _iter8
        extension_iteration = iteration
    else:
        iteration = ''
        extension_iteration = '_iter0'
    folder = "/data/test_results/"
    crawlers = ['safariProfile2', 'chromeProfile','safariProfile1Copy']
    files_by_crawler = {
        'safariProfile1': {
            'cookies': folder + 'safariProfile1/cookies/'+safari1_cookie_file,
            'localStorage': folder +'safariProfile1/localStorage/'+safari1_cookie_file.replace('cookies', 'localStorage'),
            'extensionRequests': folder + 'safariProfile1/extensionRequests/'+safari1_cookie_file.replace('cookies', 'extensionRequests').replace('extensionRequests'+iteration, extension_iteration+'_extensionRequests').replace('__','_')
        }
    }

    # Now find the redo crawler, it'll have a different timestamp
    seeder_domain = prefix.split('_')[-1]
    substring = seeder_domain+'_cookies'+iteration
    for crawler in crawlers:
        if iteration == '':
            extension_iteration = '_iter0'
            if crawler == 'safariProfile1Copy':
                iteration = '_iter0'
        else:
            extension_iteration = iteration
            
        for filename in cookie_filenames[crawler]:
            if substring in filename:
                files_by_crawler[crawler] = {
                    'cookies': folder + crawler + '/cookies/'+filename,
                    'localStorage': folder + crawler + '/localStorage/'+filename.replace('cookies', 'localStorage'),
                    'extensionRequests': folder + crawler + '/extensionRequests/'+filename.replace('cookies', 'extensionRequests').replace('_extensionRequests'+iteration, extension_iteration+'_extensionRequests').replace('__','_'),
                }
                break
    return files_by_crawler

# Globals (yes, I know :( )
# csv_header_bounce_tracking_results = 'redirect_chain_id,seeder_domain,start_url,src_ts,src_value,src_name,src_domain,src_domain_sld,src_frame_tree,src_frame_id,src_frame_domain,src_frame_domain_sld,'+ \
#                     'src_top_level_frame_id,src_top_level_frame_domain,src_top_level_frame_domain_sld,src_resource_type,src_query_id,src_previous_top_level_url,src_1p_context,' + \
#                     'dst_ts,dst_value,dst_name,dst_domain,dst_domain_sld,dst_frame_tree,dst_frame_id,dst_frame_domain,dst_frame_domain_sld,' + \
#                     'dst_top_level_frame_id,dst_top_level_frame_domain,dst_top_level_frame_domain_sld,dst_resource_type,dst_query_id,dst_previous_top_level_url,dst_1p_context,' + \
#                     'transfer_type,destination_collection_type,length_of_chain,urls_in_redirect_chains,crawler'

files_with_missing_doc_reqs = set([])
current_file = ''
tl_sites_visited = {} # Number of sites visited as top level frames
url_chains = {}

def analyze():
    # Clear outfile
    outfile_name = 'results_two_crawlers_only_4-26.json' # '/data/test_results/test_redirect_chains_from_parallel_crawls.txt'
    outfile = open(outfile_name, 'w')
    outfile.close()

    # Open outfile for writing
    outfile = open(outfile_name, 'a')
    # outfile.write(csv_header_bounce_tracking_results+'\n')
    # outfile.write('[\n')

    stats_file_name = 'tmp_stats.csv'

    crawlers = ['safariProfile1', 'safariProfile2', 'chromeProfile', 'safariProfile1Copy']
    cookie_filenames = {
        'safariProfile1Copy': os.listdir('/data/test_results/safariProfile1Copy/cookies'),
        'safariProfile2': os.listdir('/data/test_results/safariProfile2/cookies'),
        'chromeProfile': os.listdir('/data/test_results/chromeProfile/cookies'),
    }

    for filename in os.listdir('/data/test_results/safariProfile1/cookies'): # ['02-15-2022_13:54:12_PM_basketball-reference.com_cookies_iter3.csv']: #  ['02-16-2022_17:06:04_PM_instagr.am_cookies.csv', '02-16-2022_17:06:04_PM_instagr.am_cookies_iter1.csv']
        if 'failed_attempt' in filename:
            continue
        redirect_chains_by_crawler = {}
        repeated_tokens_by_crawler = {}
        repeated_tokens_by_crawler_and_cid = {}
        repeated_token_names_by_crawler = {}
        non_uid_names = set([])
        
        files = getFilesFromCrawl(filename, cookie_filenames)
        for crawler in files:
            current_file = files[crawler]['extensionRequests']
            evasion_detector = EvasionDetector('/data/test_results/'+crawler, crawler)
            print('reconstructEvents on', crawler)
            redirect_chains, repeated_tokens, _ = evasion_detector.reconstructEvents(files[crawler])
            if not redirect_chains:
                continue

            repeated_tokens_by_crawler[crawler] = set([])
            repeated_tokens_by_crawler_and_cid[crawler] = repeated_tokens
            redirect_chains_by_crawler[crawler] = redirect_chains
            repeated_token_names_by_crawler[crawler] = {}
            for cid in redirect_chains:
                for event in redirect_chains[cid]:
                    if event.name not in repeated_token_names_by_crawler[crawler]:
                        repeated_token_names_by_crawler[crawler][event.name] = set([])
                    repeated_token_names_by_crawler[crawler][event.name].add(event.value)
            
            for name in repeated_token_names_by_crawler[crawler]:
                if len(repeated_token_names_by_crawler[crawler][name]) > 1:
                    # This is definitely not a UID.
                    non_uid_names.add(name)

            for cid in repeated_tokens:
                for token in repeated_tokens[cid]:
                    repeated_tokens_by_crawler[crawler].add(token)
            
        all_tokens, repeated_tokens_by_crawler, repeated_token_names_by_crawler = removeNonUids(repeated_tokens_by_crawler, repeated_token_names_by_crawler, non_uid_names)
        uid_tokens = getUidTokensByTwoCrawlersOnly(all_tokens, repeated_tokens_by_crawler, repeated_token_names_by_crawler)
        print('UID tokens:', uid_tokens)

        clean_redirect_chains_per_crawler = {}
        clean_repeated_token_names_by_crawler = {}
        for crawler in redirect_chains_by_crawler:
            dirty_redirect_chains = redirect_chains_by_crawler[crawler]
            redirect_chains = {}
            # Remove redirect chains that contain tokens transferred across 1p contexts, but NONE of those tokens are UIDs.
            # Also remove redirect chains that, once they have all non-UID tokens stripped from them, contain no more repeated tokens.
            for chain_id in dirty_redirect_chains:
                contexts_per_token = {}
                for event in dirty_redirect_chains[chain_id]:
                    token = event.value
                    if token not in uid_tokens:
                        continue
                    if token not in contexts_per_token:
                        contexts_per_token[token] = set([])
                    contexts_per_token[token].add(event.get1pContext())
                if len(contexts_per_token.keys()) == 0:
                    # No tokens were found that were UIDs
                    continue
                max_contexts = max([len(contexts_per_token[token]) for token in contexts_per_token])
                if max_contexts < 2:
                    print('ERROR: FOUND CHAIN WITH FEWER THAN TWO CONTEXTS')
                    continue
                redirect_chains[chain_id] = dirty_redirect_chains[chain_id]
            if redirect_chains != {}:
                clean_redirect_chains_per_crawler[crawler] = redirect_chains
                # Make a map of names to token values
                clean_repeated_token_names_by_crawler[crawler] = {}
                for cid in redirect_chains:
                    for event in redirect_chains[cid]:
                        if event.value not in uid_tokens:
                            continue
                        clean_repeated_token_names_by_crawler[crawler][event.name] = token
        
        crawlers_per_token, names_per_token_per_crawler = crawlersPerToken(uid_tokens, clean_repeated_token_names_by_crawler, clean_redirect_chains_per_crawler)
        for crawler in clean_redirect_chains_per_crawler:
            seen = []
            redirect_chains = clean_redirect_chains_per_crawler[crawler]
            for cid in redirect_chains:
                print(crawler, 'chain:', cid)
                print('\t', redirect_chains[cid][0].query_id, redirect_chains[cid][0].get1pContext())
                for event in redirect_chains[cid]:
                    if event.resource_type != 'document' or event.query_id in seen:
                        continue
                    seen.append(event.query_id)
                    print('\t', event.query_id, event.get1pContext())

            # Print the human-readable stuff
            print(crawler, filename+':')
            for chain_id in redirect_chains:
                print('    Redirect chain #' + str(chain_id))
                print('    line_number, frame_tree, event_type, request_resource_type, 1p_context, query_domain, token, token_name')
                for event in redirect_chains[chain_id]:
                    if event.value not in uid_tokens:
                        continue
                    print('       ', event.ts, event.query_id+1, event.frame_tree, event.event_type, event.resource_type, event.get1pContext(), event.domain, event.value, event.name)

            # Create the JSON output file
            for chain_id in redirect_chains:
                all_results = evasion_detector.fitIntoTaxonomy(redirect_chains[chain_id], chain_id, uid_tokens, crawlers_per_token, names_per_token_per_crawler[crawler], crawler=crawler)
                for results in all_results:
                    json_results = json.dumps(results)
                    outfile.write(json_results+'\n')
        
    outfile.close()

    # stats_file = open(stats_file_name, 'w')
    # stats_file.write('top_level_domain,count\n')
    # for site in tl_sites_visited:
    #     stats_file.write(site+','+str(tl_sites_visited[site])+'\n')
    # stats_file.close()
    
    # url_chain_file = open('url_chains.csv', 'w')
    # url_chain_file.write('seeder,url_chain\n')
    # for seeder in url_chains:
    #     for url_chain in url_chains[seeder]:
    #         url_chain_file.write(seeder+','+url_chain+'\n')

    # for f in files_with_missing_doc_reqs:
    #     print(f)

def redirectChainsWithoutUids():
    # Clear outfile
    outfile_name = 'bounce_tracking_without_uids.csv' # '/data/test_results/test_redirect_chains_from_parallel_crawls.txt'
    outfile = open(outfile_name, 'w')
    outfile.close()
    outfile = open(outfile_name, 'a')

    crawlers = ['safariProfile1', 'safariProfile2', 'chromeProfile', 'safariProfile1Copy']
    cookie_filenames = {
        'safariProfile1Copy': os.listdir('/data/test_results/safariProfile1Copy/cookies'),
        'safariProfile2': os.listdir('/data/test_results/safariProfile2/cookies'),
        'chromeProfile': os.listdir('/data/test_results/chromeProfile/cookies'),
    }

    for filename in os.listdir('/data/test_results/safariProfile1/cookies'): # ['02-13-2022_21:31:47_PM_google.com.bn_cookies_iter1.csv']: # 
        if 'failed_attempt' in filename:
            continue
        redirect_chains_by_crawler = {}
        repeated_tokens_by_crawler = {}
        maybe_chains_by_crawler = {}
        repeated_tokens_by_crawler_and_cid = {}
        repeated_token_names_by_crawler = {}
        non_uid_names = set([])
        
        files = getFilesFromCrawl(filename, cookie_filenames)
        for crawler in files:
            evasion_detector = EvasionDetector('/data/test_results/'+crawler, crawler)
            redirect_chains, repeated_tokens, chains_maybe_wo_uids = evasion_detector.reconstructEvents(files[crawler])
            if not redirect_chains:
                continue

            repeated_tokens_by_crawler[crawler] = set([])
            repeated_tokens_by_crawler_and_cid[crawler] = repeated_tokens
            redirect_chains_by_crawler[crawler] = redirect_chains
            maybe_chains_by_crawler[crawler] = chains_maybe_wo_uids
            repeated_token_names_by_crawler[crawler] = {}
            for cid in redirect_chains:
                for event in redirect_chains[cid]:
                    if event.name not in repeated_token_names_by_crawler[crawler]:
                        repeated_token_names_by_crawler[crawler][event.name] = set([])
                    repeated_token_names_by_crawler[crawler][event.name].add(event.value)
            
            for name in repeated_token_names_by_crawler[crawler]:
                if len(repeated_token_names_by_crawler[crawler][name]) > 1:
                    # This is definitely not a UID.
                    non_uid_names.add(name)

            for cid in repeated_tokens:
                for token in repeated_tokens[cid]:
                    repeated_tokens_by_crawler[crawler].add(token)

        all_tokens, repeated_tokens_by_crawler, repeated_token_names_by_crawler = removeNonUids(repeated_tokens_by_crawler, repeated_token_names_by_crawler, non_uid_names)
        uid_tokens = getUidTokens(all_tokens, repeated_tokens_by_crawler, repeated_token_names_by_crawler)
        
        chains_wo_uids = []
        for crawler in maybe_chains_by_crawler:
            for chain_id in maybe_chains_by_crawler[crawler]:
                found_uid_token = False
                for event in maybe_chains_by_crawler[crawler][chain_id]:
                    if event.value in uid_tokens:
                        found_uid_token = True
                if not found_uid_token:
                    chains_wo_uids.append(maybe_chains_by_crawler[crawler][chain_id])
        
        all_chains = []
        for chain in chains_wo_uids:
            urls_in_redirect_chain = []
            for event in chain:
                if event.resource_type != 'document' or '-' in event.frame_tree or (len(urls_in_redirect_chain) > 0 and urls_in_redirect_chain[-1] == event.url) or event.url == '':
                    continue
                if len(urls_in_redirect_chain) == 0:
                    urls_in_redirect_chain.append(event.previous_top_level_url)
                urls_in_redirect_chain.append(event.url)
            if urls_in_redirect_chain not in all_chains:
                all_chains.append(urls_in_redirect_chain)
        
        for chain in all_chains:
            outfile.write(','.join(['`'+url+'`' for url in urls_in_redirect_chain])+'\n')
    
    outfile.close()

if __name__ == "__main__":
    analyze()
    # redirectChainsWithoutUids()