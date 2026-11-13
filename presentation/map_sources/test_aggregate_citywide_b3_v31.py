import unittest
import pandas as pd
from aggregate_citywide_b3_v31 import summarize, N7, N13

class PairingTests(unittest.TestCase):
    def test_pair_first_and_distinguish_unknown_uncovered_and_true_zero(self):
        rows=[dict(origin_id=str(i),blocksnet_block_id='A',network_covered=True,**{N7:a,N13:b})
              for i,(a,b) in enumerate([(0,1),(1,100),(100,101)])]
        rows += [dict(origin_id='3',blocksnet_block_id='A',network_covered=False,**{N7:0,N13:999}),
                 dict(origin_id='4',blocksnet_block_id='A',network_covered=True,**{N7:None,N13:3}),
                 dict(origin_id='5',blocksnet_block_id='B',network_covered=True,**{N7:0,N13:0}),
                 dict(origin_id='6',blocksnet_block_id=None,network_covered=True,**{N7:9,N13:10})]
        out=summarize(pd.DataFrame(rows)).set_index('blocksnet_block_id')
        self.assertEqual(out.loc['A','median_delta_N'],1) # not median(N13)-median(N7)=99
        self.assertEqual(out.loc['A','n_origins'],5)
        self.assertEqual(out.loc['A','n_valid'],3)
        self.assertEqual(out.loc['A','n_uncovered'],1)
        self.assertEqual(out.loc['A','n_unknown'],1)
        self.assertEqual(out.loc['B','median_delta_N'],0)
        self.assertEqual(out.loc['B','n_valid'],1)
    def test_missing_coverage_is_rejected(self):
        x=pd.DataFrame([dict(origin_id='0',blocksnet_block_id='A',network_covered=None,**{N7:0,N13:0})])
        with self.assertRaises(ValueError): summarize(x)

if __name__=='__main__': unittest.main()
