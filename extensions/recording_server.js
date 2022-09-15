const http = require('http')
const resultsWriter = require('../lib/write_results')

const createBrowserState = _ => {
    const state = {};
    state.init = _ => {
        state.topLevelFrameDomains = {
            'safariProfile1': {},
            'safariProfile1Copy': {},
            'safariProfile2': {},
            'chromeProfile': {}
        };
        state.output_files = {
            'safariProfile1': '',
            'safariProfile1Copy': '',
            'safariProfile2': '',
            'chromeProfile': ''
        };
        state.request_events = {
            'safariProfile1': [],
            'safariProfile1Copy': [],
            'safariProfile2': [],
            'chromeProfile': []
        };
    };

    state.clear = profile => {
        state.topLevelFrameDomains[profile] = {};
        state.request_events[profile] = [];
    }

    state.init();
    return state;
}

const getProfile = profile_name => {
    if (profile_name.includes('/data/profiles')) {
        return profile_name.split('/')[3];
    } else {
        return profile_name;
    }
}

const parseMessages = body => {
    profile = getProfile(body.profile);
    if ('START' in body) {
        state.output_files[profile] = body['START'];
        console.log('Received start command for', profile, 'output file is', state.output_files[profile]);
        return;
    } else if ('END' in body) {  
        console.log('Writing requests to file for', profile);
        //console.log('state.request_events[profile]:', state.request_events[profile], 'state.output_files[profile]:', state.output_files[profile])
        if (profile === 'safariProfile1Copy') {
            resultsWriter.writeCrawlEvents(state.request_events['safariProfile1'], state.output_files[profile]);
        } else {
            resultsWriter.writeCrawlEvents(state.request_events[profile], state.output_files[profile]);
        }
        state.clear(profile);
        console.log('After clearing profile, length of requests is', state.request_events[profile].length);
        return;
    } 
    for (const request_number in body) {
        if (request_number === 'profile') {
            continue;
        } else if (request_number === 'error') {
            console.log('ERROR in extension for', profile, 'in', state.output_files[profile], ':', body['error']);
            continue;
        }
        console.log('Request for', profile);
        const header = ['url', 'type', 'time', 'frameId', 'frameDomain', 'frameTree', 'topLevelFrameDomain', 'expectedUrl', 'resourceType', 'redirectTo', 'isRedirect', 'redirectDomain', 'queryParams', 'cookie'];
        // Msg will contain: frameId: 0
        // initiator: "https://cse.ucsd.edu"
        // method: "GET"
        // parentFrameId: -1
        // requestId: "245906"
        // tabId: 537
        // timeStamp: 1643325376226.835
        // type: "main_frame"
        // url: "https://grad.ucsd.edu/academics/progress-to-degree/advancing-to-candidacy.html#Doctoral-Students"
        const msg = body[request_number];
        const parsed_msg = {};

        if (msg.type === 'main_frame') {
            // This is a document request. Presumably, it changed the topLevelFrameDomain.
            if (msg.frameId !== 0) {
                console.log('ERROR: I thought main_frame requests were only for top level frames but that\'s not true.');
            }
            state.topLevelFrameDomains[profile][msg.tab_id] = msg.url;
        } 
        if (msg.type === 'sub_frame' && !('initiator' in msg)) {
            console.log('ERROR: Subframe didn\'t have an initiator, we need a map of frames to domains.')
        }

        parsed_msg.url = msg.url;
        parsed_msg.type = 'request';
        parsed_msg.time = parseFloat(msg.timeStamp)*1000;
        parsed_msg.frameId = msg.frameId;
        
        parsed_msg.frameDomain = 'initiator' in msg ? msg.initiator : msg.url;
        if (msg.parentFrameId === -1) {
            parsed_msg.frameTree = msg.frameId;
        } else {
            parsed_msg.frameTree = msg.frameId.toString() + '-' + msg.parentFrameId.toString();
        }
        parsed_msg.topLevelFrameDomain = state.topLevelFrameDomains[profile][msg.tab_id];
        parsed_msg.resourceType = (msg.type === 'main_frame') ? 'document' : msg.type;

        state.request_events[profile].push(parsed_msg);
    }
}

const requestListener = async (request, response) => {
    let msg_body = '';
    for await (const chunk of request) {
        msg_body += chunk.toString();
    }
    const full_body = JSON.parse(msg_body);
    response.writeHead(200);
    response.end();

    parseMessages(full_body);
}

console.log('Recording server starting up...');
const state = createBrowserState();
const server = http.createServer(requestListener);
server.listen(8086);