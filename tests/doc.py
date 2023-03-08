from xooai import Text

def test_text():
    t1 = Text(text='Aa')
    t2 = Text(ref='test.txt')
    assert t1.text == 'Aa'
    assert t2.ref == 'test.txt'