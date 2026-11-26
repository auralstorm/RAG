import type { MockRequest as Request, MockResponse as Response } from './types';
import { fakeList } from './utils';

function getFakeList(req: Request, res: Response) {
  const params: Record<string, string> = req.query;

  const count = params.count * 1 || 20;

  const result = fakeList(count);
  return res.json({
    data: {
      list: result,
    },
  });
}

export default {
  'GET /api/fake_list': getFakeList,
};