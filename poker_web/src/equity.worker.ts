import { calculateEquity, type EquityInput } from './equity';
self.onmessage = (event: MessageEvent<EquityInput>) => {
  try { self.postMessage({ key: event.data.key, result: calculateEquity(event.data) }); }
  catch { self.postMessage({ key: event.data.key, result: null }); }
};
