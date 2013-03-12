from collections import defaultdict
split_strategies = { #doubled_card:{dealer_card:action}
            '1':defaultdict(lambda: 'splt'),
            '2':defaultdict(lambda: 'hitt', {
                '2':'splt',
                '3':'splt',
                '4':'splt',
                '5':'splt',
                '6':'splt',
                '7':'splt'}),
            '3':defaultdict(lambda: 'hitt', {
                '2':'splt',
                '3':'splt',
                '4':'splt',
                '5':'splt',
                '6':'splt',
                '7':'splt'}),
            '4':defaultdict(lambda: 'hitt', {
                '5':'splt',
                '6':'splt'}),
            '5':defaultdict(lambda: 'down', {
                'T':'hitt',
                '1':'hitt'}),
            '6':defaultdict(lambda: 'splt',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            '7':defaultdict(lambda: 'splt',{
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            '8':defaultdict(lambda: 'splt'),
            '9':defaultdict(lambda: 'splt',{
                '7':'stay',
                'T':'stay',
                '1':'stay'}),
            'T':defaultdict(lambda: 'stay')
            }
ace_present_strategies = {#othercardsum:{dealer_card:action}
            2:defaultdict(lambda:'hitt', {
                '5':'down',
                '6':'down'}),
            3:defaultdict(lambda:'hitt',{
                '5':'down',
                '6':'down'}),
            4:defaultdict(lambda:'hitt',{
                '4':'down',
                '5':'down',
                '6':'down'}),
            5:defaultdict(lambda:'hitt',{
                '4':'down',
                '5':'down',
                '6':'down'}),
            6:defaultdict(lambda:'hitt',{
                '3':'down',
                '4':'down',
                '5':'down',
                '6':'down'}),
            7:defaultdict(lambda:'down',{
                '2':'stay',
                '7':'stay',
                '8':'stay',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            8:defaultdict(lambda:'stay'),
            9:defaultdict(lambda: 'stay'),
            10:defaultdict(lambda: 'stay')
            }
general_strategies = {#cardsum:{dealer_card:action}
            5:defaultdict(lambda: 'hitt'),
            6:defaultdict(lambda: 'hitt'),
            7:defaultdict(lambda: 'hitt'),
            8:defaultdict(lambda: 'hitt'),
            9:defaultdict(lambda: 'hitt',{
                '3':'down',
                '4':'down',
                '5':'down',
                '6':'down'}),
            10:defaultdict(lambda: 'down',{
                'T':'hitt',
                '1':'hitt'}),
            11:defaultdict(lambda: 'down',{
                '1':'hitt'}),
            12:defaultdict(lambda: 'hitt',{
                '4':'stay',
                '5':'stay',
                '6':'stay'}),
            13:defaultdict(lambda: 'stay',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            14:defaultdict(lambda: 'stay',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            15:defaultdict(lambda: 'stay',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            16:defaultdict(lambda: 'stay',{
                '7':'hitt',
                '8':'hitt',
                '9':'hitt',
                'T':'hitt',
                '1':'hitt'}),
            17:defaultdict(lambda:'stay'),
            18:defaultdict(lambda:'stay'),
            19:defaultdict(lambda:'stay'),
            20:defaultdict(lambda:'stay'),
            21:defaultdict(lambda:'stay')
        }


