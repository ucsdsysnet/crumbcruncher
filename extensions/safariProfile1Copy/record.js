const all_requests = {
    'profile': 'safariProfile1Copy'
};
var num_requests = 0;

const clearAllRequests = () => {
    for (const key in all_requests) {
        if (key !== 'profile') {
            delete all_requests[key];
        }
    }
};

const sendRequests = () => {
    if (Object.keys(all_requests).length === 1 && 'profile' in all_requests) {
        return;
    }

    var clearRequests = true;
    var xhr = new XMLHttpRequest();
    try {
        xhr.open("POST", "http://localhost:8086/");
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.send(JSON.stringify(all_requests));
    } catch (err) {
        clearRequests = false;
        if ('error' in all_requests) {
            all_requests['error'].push(err.toString());
        } else {
            all_requests['error'] = [err.toString()];
        }
    }
    if (clearRequests) {
        clearAllRequests();
        console.log('Length of all_requests:', Object.keys(all_requests).length);
    }
};

chrome.webRequest.onBeforeRequest.addListener(
    function(details) {
        if (details.url === 'http://localhost:8086/') {
            return;
        }
        console.log('Request for ', details.type, details.url);
        all_requests[num_requests] = details;
        num_requests += 1;
    },
  {urls: ["<all_urls>"]}
);

setInterval(sendRequests, 1000);