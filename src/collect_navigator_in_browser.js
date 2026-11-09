/* Run in DevTools Console on https://dopobr.petersburgedu.ru/.
 * Public list only; no credentials copied, no guessed details API.
 * Downloads original pages even if collection stops with an error.
 */
(async () => {
  if (location.hostname !== 'dopobr.petersburgedu.ru') {
    throw new Error('Open the Navigator site first');
  }
  const bundle = {format: 'navigator-public-pages-v1', pages: [], error: null};
  let url = '/api/program/list_odo/?district=2&limit=10&offset=0&ordering=rating_avg_desc&page=1';
  const seen = new Set();
  const controller = new AbortController();
  window.stopNavigatorCollection = () => controller.abort();
  try {
    for (let page = 0; url && page < 200; page++) {
      const target = new URL(url, location.origin);
      if (target.origin !== location.origin || target.pathname !== '/api/program/list_odo/') {
        throw new Error('Unexpected pagination URL');
      }
      if (seen.has(target.href)) throw new Error('Pagination cycle');
      seen.add(target.href);
      if (page) await new Promise(resolve => setTimeout(resolve, 1000));
      const response = await fetch(target, {credentials: 'omit', signal:
        AbortSignal.any([controller.signal, AbortSignal.timeout(20000)])});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data.results) || !Number.isInteger(data.count) || !('next' in data)) {
        throw new Error('Unrecognized response');
      }
      bundle.pages.push({url: target.href, response: data});
      console.log(`Страница ${page + 1}; записей ${bundle.pages.reduce((n,p)=>n+p.response.results.length,0)} / ${data.count}`);
      if (data.next && !data.results.length) throw new Error('Empty page with next link');
      url = data.next;
    }
    if (url) bundle.error = 'Page limit reached; partial collection';
  } catch (error) {
    bundle.error = String(error);
    console.error('Сбор остановлен; сохранится полученная часть:', error);
  } finally {
    delete window.stopNavigatorCollection;
    const blobURL = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = blobURL;
    link.download = 'navigator-vasileostrovsky-pages.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(blobURL), 10000);
    console.log('JSON подготовлен к скачиванию. Это список программ, пока без проверки возрастов и адресов групп.');
  }
})();
