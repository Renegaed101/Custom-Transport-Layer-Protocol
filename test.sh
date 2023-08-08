#!/bin/bash
echo Test1;
diff little.txt write1.txt;
echo Test2;
diff little1.txt write2.txt;
echo Test3
diff little2.txt write3.txt;
echo Test4;
diff little.txt write4.txt;
echo Test5;
diff little1.txt write5.txt;
echo Test6;
diff little2.txt write6.txt;
echo Test7;
diff medium.txt write7.txt;
echo Test8;
diff medium.txt write8.txt;
echo Test9;
diff tiny.txt write9.txt;
echo Test10;
diff tiny1.txt write10.txt;
echo Test11;
diff tiny.txt write11.txt
echo Test12
diff tiny1.txt write12.txt 
echo Test13
diff large.txt write13.txt
echo Test14
diff large.txt write14.txt
sudo rm write1.txt write2.txt write3.txt write4.txt write5.txt write6.txt write7.txt write8.txt write9.txt write10.txt write11.txt write12.txt write13.txt write14.txt