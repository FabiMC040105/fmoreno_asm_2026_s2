#include <cstdio>
#include <vector>
#include "fir_esp32.h"
int main(int argc,char**argv){
 if(argc!=3)return 2;
 FILE*fi=fopen(argv[1],"rb");if(!fi)return 3;std::vector<float>x;float v;while(fread(&v,4,1,fi)==1)x.push_back(v);fclose(fi);
 FIRLowPass129 fir;std::vector<float>y(x.size());for(size_t i=0;i<x.size();++i)y[i]=fir.process(x[i]);
 FILE*fo=fopen(argv[2],"wb");if(!fo)return 4;fwrite(y.data(),4,y.size(),fo);fclose(fo);printf("OK %zu muestras FIR\n",y.size());return 0;
}
