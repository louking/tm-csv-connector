// constants
const CHECK_TABLE_UPDATE = 1000;     // ms, interval to check for table updates
const RESULTS_COOKIE_TIMEOUT = 5000; // ms, timeout for cookie mutex

// mutex
let results_cookie_mutex = new MutexPromise('results-cookie', {timeout: RESULTS_COOKIE_TIMEOUT});
