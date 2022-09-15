var empty_requests = {
    'profile': 'safariProfile1Copy'
};
var all_requests = empty_requests;
var num_requests = 0;

const clearAllRequests = () => {
    all_requests = empty_requests;
};

const sendRequests = () => {
    if (Object.keys(all_requests).length === 1 && 'profile' in all_requests) {
        return;
    }
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "http://localhost:8086/");
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.send(JSON.stringify(all_requests));
    clearAllRequests();
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