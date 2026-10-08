const WINDOW_MS = 60_000;
const MAX_SEARCHES = 4;

// Each object belongs to one IP-derived identifier; it stores only four times.
export class SearchCounter {
  constructor(ctx){ this.ctx = ctx; }

  async fetch(){
    const storage = this.ctx.storage;
    const now = Date.now();
    const result = storage.transactionSync(() => {
      const times = (storage.kv.get('times') || []).filter(time => time > now - WINDOW_MS);
      if (times.length >= MAX_SEARCHES) return {success:false};
      times.push(now);
      storage.kv.put('times', times);
      return {success:true};
    });
    if (result.success) await storage.setAlarm(now + WINDOW_MS);
    return Response.json(result);
  }

  async alarm(){
    const storage = this.ctx.storage;
    const times = storage.kv.get('times') || [];
    const expires = (times.at(-1) || 0) + WINDOW_MS;
    if (expires > Date.now()) await storage.setAlarm(expires);
    else await storage.deleteAll();
  }
}
