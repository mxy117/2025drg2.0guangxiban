from enum import Enum
import os
import sys
import time
import re
import pandas as pd
from collections import namedtuple
from Grouper_chs_drg_20 import Grouper_chs_drg_20 as Grouper
from Base import Reader,MedicalRecord,DrgGroupStatus,GroupResult,tuple_to_str,remove_last_zero

class GroupProxy:
  def __init__(self,**kwargs):
    self.DEBUG=kwargs.get('DEBUG') if 'DEBUG' in kwargs else 0
    self.TRANS_CODE=kwargs.get('TRANS_CODE') if 'TRANS_CODE' in kwargs else 0
    self.load_data()
    self.grouper=Grouper(**kwargs)
    self.check_messages=[]
    
  def load_data(self):
    # 初始化数据读取器，指定数据存储目录为'DATA'（数据文件夹）
    reader=Reader('DATA')
    # 读取诊断信息CSV文件（ZD_INFO.csv）并转换为字典，键值对格式存储诊断编码与详细信息
    self.ZD_INFO=reader.read('ZD_INFO').to_dict()
    # 读取手术操作信息CSV文件（SS_INFO.csv）并转换为字典，键值对格式存储手术编码与详细信息
    self.SS_INFO=reader.read('SS_INFO').to_dict()
    # 读取诊断编码映射CSV文件（ZD_MAP.csv）并转换为字典，键为原始编码，值为分组器支持的目标编码
    self.ZD_MAP=reader.read('ZD_MAP').to_dict()
    # 读取手术编码映射CSV文件（SS_MAP.csv）并转换为字典，键为原始编码，值为分组器支持的目标编码
    self.SS_MAP=reader.read('SS_MAP').to_dict()

  def message(self,*args):
    message=' '.join(args)
    self.check_messages.append(message)

  def return_messages(self):
    result=self.check_messages.copy()
    self.check_messages.clear()
    return result

  def group_df(self,df,writer,cols=[]):
    if cols:
      df.index.name=MedicalRecord._fields[0]
      df.rename(columns=dict(zip(cols[1:],MedicalRecord._fields[1:])),inplace=True)
    df = df.fillna('').astype(object)
    print('record count',len(df))
    t1=time.time()
    results=self.group_iter(df.itertuples())
    columns=list(df.columns)
    if cols:
      for x,y in zip(cols[1:],MedicalRecord._fields[1:]):
        columns[columns.index(y)]=x
      df.index.name=cols[0]
    writer.write('{},{},{}\n'.format(df.index.name,','.join(columns),','.join(GroupResult._fields)))
    while True:
        try:
          writer.write(tuple_to_str(next(results))+'\n')
        except StopIteration:
          break
    t2=time.time()
    print('group time',int((t2-t1)*1000))

  def group_iter(self,it):
    while True:
      try:
        record=next(it)
      except StopIteration:
        break
      yield record+self.group(record)

  def group(self,record):
    if self.TRANS_CODE:
      trans_result=self.trans(record)
      if isinstance(trans_result,DrgGroupStatus):
        result=GroupResult(record.Index,trans_result.value,self.return_messages(),'0000','00','0000')
        if self.DEBUG:
          print(result)
        return result
      record=trans_result
    else:
      record=record._replace(zdList=re.split(r',|\|',record.zdList))
      if record.ssList:
        ss_list_str = record.ssList if isinstance(record.ssList, str) else ''
        record = record._replace(ssList=re.split(r',|\|', ss_list_str))
      else:
        record=record._replace(ssList=[])
    check_result=self.check(record)
    if check_result:
      result=GroupResult(record.Index,check_result.value,self.return_messages(),'0000','00','0000')
    else:
      result=self.grouper.group(record)
      group_messages=result.messages
      for message in reversed(self.return_messages()):
        group_messages.insert(0,message)
    return result

  def trans(self,record):
    # zd_list=record.zdList.split(',')
    zd_list=re.split(',|\\|',record.zdList)
    zd_no_map=[]
    for x in zd_list:
      if x in self.ZD_MAP:
        zd=self.ZD_MAP.get(x)
        if zd!=x:
          zd_list[zd_list.index(x)]=self.ZD_MAP.get(x)
          # self.message('{}->{}'.format(x,zd))
      else:
        zd_list[zd_list.index(x)]=''
        zd_no_map.append(x)
    if zd_list and zd_list[0]=='-':
      zd_no_map.append(record.zdList.partition(',')[0])
    if zd_no_map:
      self.message('诊断{}无法转换为分组器支持的编码'.format('、'.join(zd_no_map)))
      return DrgGroupStatus.ZD_NOT_MAPPING
    record=record._replace(zdList=[x for x in zd_list if x and x!='-'])
    if not record.ssList:
      record=record._replace(ssList=[])
      return record
    # ss_list=record.ssList.split(',')
    ss_list=re.split(',|\\|',record.ssList)
    ss_no_map=[]
    for x in ss_list:
      if x in self.SS_MAP:
        ss=self.SS_MAP.get(x)
        if ss!=x:
          ss_list[ss_list.index(x)]=self.SS_MAP.get(x)
          # self.message('{}->{}'.format(x,ss))
      else:
        ss_list[ss_list.index(x)]=''
        ss_no_map.append(x)
    if ss_list and ss_list[0]=='-':
      ss_no_map.append(record.ssList.partition(',')[0])
    if ss_no_map:
      self.message('手术操作{}无法转换为分组器支持的编码'.format('、'.join(ss_no_map)))
      return DrgGroupStatus.SS_NOT_MAPPING
    record=record._replace(ssList=[x for x in ss_list if x and x!='-'])
    return record

  def check(self,record):
    try:
      if record.gender==None:
        self.message('病人性别为空')
        return DrgGroupStatus.CHECK_FAILED
      if not (record.gender in [1,'1','男'] or record.gender in [2,'2','女']):
        self.message('病人性别取值必须为1或2：{}'.format(record.gender))
        return DrgGroupStatus.CHECK_FAILED
      if record.age==None:
        self.message('病人年龄为空')
        return DrgGroupStatus.CHECK_FAILED
      if int(record.age)==0 and record.ageDay==None:
        self.message('病人年龄0时，年龄天数必须有值')
        return DrgGroupStatus.CHECK_FAILED
      if int(record.age)==0 and int(record.ageDay)<=28 and record.weight==None:
        self.message('新生儿的出生体重必须有值')
        return DrgGroupStatus.CHECK_FAILED
      if not record.zdList:
        self.message('诊断信息为空')
        return DrgGroupStatus.CHECK_FAILED
    except:
      self.message('病案信息解析出错')
      return DrgGroupStatus.CHECK_FAILED
    for x in record.zdList:
      self.message('{} {}'.format(x,self.ZD_INFO.get(x,'未知名称')))
    for x in record.ssList:
      self.message('{} {}'.format(x,self.SS_INFO.get(x,'未知名称')))
    return 

  def group_record(self,record_str):
    record=MedicalRecord(**dict(zip(MedicalRecord._fields,map(remove_last_zero,replace_csv(record_str).split(',')))))
    return self.group(record)

  def group_txt(self):
    path=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    lines=open(os.path.join(path,'input.txt')).read().splitlines()
    if len(lines)==0:
      print('input.txt文件无数据')
      sys.exit(-1)
    file=open(os.path.join(path,'output.txt'),'w')
    for line in lines[1:]:
      file.write(str(self.group_record(line))+'\n')

  def group_csv(self,filename,cols):
    filename=filename.replace('.csv','')  # 添加第二个参数为空字符串
    import pandas as pd
    # 定义结果文件路径变量
    csv_output_file_result = filename + '_result.csv'
    # 读取输入CSV文件
    df=pd.read_csv(filename+'.csv',index_col=cols[0])  # 读取时需要加回.csv扩展名
    # 调用分组处理函数，将结果写入定义好的结果文件
    self.group_df(df,open(csv_output_file_result,'w',encoding='utf-8-sig'),cols)
    # 返回结果文件路径
    return csv_output_file_result

def replace_csv(csv):
  matches=re.compile("\"(.*?)\"").finditer(csv)
  for m in matches:
    if m:
      csv=csv.replace(m.group(0),m.group(1).replace(',','|'))
  return csv

if __name__ == "__main__":
  grouper=GroupProxy()
  record=MedicalRecord(Index='1653890', age=10, ageDay=21, weight=3200, gender='2', dept='28',inHospitalTime=14,leavingType='1',
  zdList='S06.500,I21.900x011,I62.001,G93.501,S06.202,I63.908,S02.900x002,J98.414,J96.000,J81.x00x002', 
  ssList='96.7201,01.2400x005,03.3100x001,33.2403,31.1x00x005,38.9301,38.9303')
  print(record)
  result=grouper.group(record)
  print(result)