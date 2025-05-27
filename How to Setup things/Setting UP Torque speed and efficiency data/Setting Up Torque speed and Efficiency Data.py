mport numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from scipy.interpolate import griddata
import os
import math
from pandas.io.excel import ExcelWriter
from stat import S_IREAD, S_IRGRP, S_IROTH
from scipy.spatial import cKDTree
#______________________________________________________________________________

#Input to be defined
#______________________________________________________________________________
MotorName = 'AF400SV'  
#Path = "C:\Work_Files\Postproccessing\Data_Final\\"
Path =  os.getcwd()
Slot = 54 # Slot number 
Pole = 16 # Pole number 
Rated_Speed = 3000

T = 6 # tun number 
VDC = 180 # DC Link Voltage 
LossLimit = 17000 #Copper Loss Limit for 20s

Temp_PM1 = 150 # reference temp used for analysis; 180 where speed > 4500
Temp_PM2 = 180 # reference temp used for analysis 

T_magnet = 150 # Magnet temp limit Put it 150 limit 
T_Limit_W = 150 # Winding average temp limit Put it 140
T_Max_W = 150 # Max winding temp limit Keep it 150 Max

Step_Torque = 2.5 # torque step required for data
Step_Speed = 250 # speed step required for data
#______________________________________________________________________________
#DO NOT ALTER THE CODE
#______________________________________________________________________________
LossRatio = 0.9 # Modulation + Loss across inverter 
VLimit = VDC * LossRatio *1/np.sqrt(2) 
N_ratedT = Rated_Speed + Step_Speed # Rated Speed which allows you to define where you set 
               # PM temp in simulaiton and set to define torque-speed curve
#______________________________________________________________________________
#LUT = pd.read_csv(Path + 'PData_Thermal_T'+ str(T) +'.csv')
LUT =  pd.read_csv('PData_Thermal_T6.csv')  # Double check if the file name and data arrangment is correct
LUT.rename(columns={'speed': 'Speed'}, inplace=True) # Replacing speed with Speed
DCR = np.mean(LUT['DCR']) # .iloc[1,17] # Taking the average resistance values of the whole column
#______________________________________________________________________________

dfx = pd.DataFrame(columns=LUT.columns)
dfx.columns = LUT.columns 
dfx.reset_index(drop=True, inplace=True)
dfx = dfx.iloc[:, 1:]
#______________________________________________________________________________

# Get Min Max values to define inputs
Min_Speed = int(LUT['Speed'].min())
Max_Speed = int(LUT['Speed'].max())

Speed_D = LUT['Speed'].values               # Getting all the values of speed
Speed_D1 =  np.unique(Speed_D, axis=0)      # Get all the unique speed values
Speed_iterations = Speed_D1.size            # Size of the unique speed values

df_result = [];   RowNoT = 0.0;   Data_Final0 = [];    
# Run a Loop for each speed
for N_Rated in Speed_D1:
    Speed = str(N_Rated)
    LUT1 = LUT[LUT['Speed'] == N_Rated]
    

    Input = LUT1[['Speed', 'current', 'Gamma']].values
    Output = LUT1.drop(columns=['Speed', 'current', 'Gamma']).reset_index()
    Output = Output.drop(Output.columns[[0,1]], axis = 1)     
    OutputT = list(Output.columns)

    # Define irregular input range
    Min_Current = int(LUT1['current'].min())         # Get min value of current
    Max_Current = int(LUT1['current'].max())         # Get max value of current
    Step_Current = int((Max_Current - Min_Current)/(101))  # Divide the current values to 101 points or 100 points
    xc_range = np.arange(Min_Current, Max_Current, Step_Current)

    # Divide the Gamma into 90 degrees
    Step_Gamma = 1
    yg_range = np.arange(int(LUT1['Gamma'].min()), int(LUT1['Gamma'].max()) \
                         + Step_Gamma,Step_Gamma)
    
    xxc, yyg = np.meshgrid(xc_range,yg_range)
       
    interp_1 = {}
    for x in OutputT:
        interp_1[x] = griddata((LUT1['current'],LUT1['Gamma']), \
                                           Output[x], (xxc, yyg), method='cubic')
        
    # Reshape 2D arrays into 1D arrays
    for key in interp_1:
        interp_1[key] = interp_1[key].flatten()
    
    xxc = xxc.flatten()
    yyg = yyg.flatten()
    
    # Create a DataFrame from the reshaped dictionary
    interp_2 = pd.DataFrame.from_dict(interp_1)
    interp_2.insert(0, 'Speed', Speed)
    interp_2.insert(2, 'Current', xxc)
    interp_2.insert(3, 'Gamma', yyg)
    # Drop rows with NaN values
    df1 = interp_2.dropna()
    df1 = df1.sort_values(by=['Current', 'Gamma'], ascending=[True, True])
    
    # Ensure the 'Speed' and 'Gamma' columns are numeric
    df1['Speed'] = pd.to_numeric(df1['Speed'], errors='coerce')
    df1['Gamma'] = pd.to_numeric(df1['Gamma'], errors='coerce')
    df1['Current'] = pd.to_numeric(df1['Current'], errors='coerce')                          

    df1_filtered = df1[(df1['VLL_rms'] <= VLimit)]
    df1_filtered2 = df1_filtered[(df1_filtered['loss_winding'] <= LossLimit)]
    df = df1_filtered2.loc[df1_filtered2.groupby('Current')['torque'].idxmax()]

    dfD = pd.DataFrame(df)
    dfD['Torque_diff'] = dfD['torque'].diff()
    dfD.fillna(0.1, inplace=True)

    # Filter out data points where y starts to decline
    threshold = 0  # Set your decline threshold
    dfD_filtered = dfD[dfD['Torque_diff'] >= threshold]
    dfD_filtered.drop(columns=['Torque_diff'], inplace=True)
    
    df_result.append(dfD_filtered)
    
df_final = pd.concat(df_result, ignore_index=True)
# _____________________________________________________________________________

Temp_PM = np.where((df_final['Speed'] <= N_ratedT), Temp_PM1, Temp_PM2)

Toruqe_adjustT = np.where((df_final['temperature_PM'] >= T_magnet)\
  | (df_final['temperature_winding_avg'] >= T_Limit_W),(-0.00083547* 90 \
+ 1.3403)/(-0.00083547*Temp_PM+1.3403), (-0.00083547*df_final['temperature_PM']\
+ 1.3403)/(-0.00083547*Temp_PM+1.3403))

df_final['torque'] = df_final['torque']* Toruqe_adjustT
df_final['TShaft'] = np.where(df_final['Speed'] < 250, df_final['torque'],\
   (df_final['torque'] -(df_final['loss_mechanical_DE']\
    + df_final['loss_mechanical_NDE']+ df_final['loss_mechanical_W']\
        + df_final['loss_stator_core'])/(df_final['Speed']/30*np.pi)))                                             
  
df_final['loss_winding'] = np.where((df_final['temperature_winding_avg'] \
  < T_Limit_W),df_final['loss_winding'], 3 * DCR * (1 +0.00393*(T_Limit_W-20))\
     * pow(df_final['Current'],2))

df_final['Total_Loss'] = df_final['loss_winding']+df_final['loss_mechanical_DE']\
   + df_final['loss_mechanical_NDE'] + df_final['loss_mechanical_W'] \
       + df_final['loss_stator_core'] + df_final['loss_rotor_PM']                                                          

df_final['Pout'] = df_final['Speed']/30*np.pi * df_final['TShaft'] 
df_final['Pin'] = df_final['Pout'] + df_final['Total_Loss']
df_final['Efficiency'] = df_final['Pout'] / df_final['Pin'] * 100
df_final['Efficiency'] = np.where(df_final['Efficiency'] < 1, 0\
                                                  ,df_final['Efficiency'])
												  

df_final = df_final[df_final['Efficiency'] <= 100]												  
df_final['LD'] = df_final['LD'] * 1000000
df_final['LQ'] = df_final['LQ'] * 1000000
df_final['Lphase'] = df_final['Lphase'] * 1000000
df_final['Lmutual'] = df_final['Lmutual'] * 1000000
df_final['FD'] = df_final['FD'] * -1
df_final['FQ'] = df_final['FQ'] * -1
df_final['Speed'] = df_final['Speed'].replace(1, 0)
#______________________________________________________________________________

# Create interpolation functions for each output
out_data = df_final.drop(columns=['Speed', 'TShaft'])

columns_to_remove = ['Speed', 'TShaft'] 
out_dataX = [col for col in df_final.columns if col not in columns_to_remove]
#------------------------------------------------------------------------------             
# Define irregular input range
#x_range = pd.DataFrame({'Speed': [int(Speed_D1[0])] \
#                + list(range(int(Speed_D1[1]) - Step_Speed,Max_Speed \
#                            + Step_Speed , Step_Speed))}) 
x_range = np.arange(0, Max_Speed + Step_Speed, Step_Speed)							
Min_Torque = int(df_final['TShaft'].min())
Min_Torque = math.ceil(Min_Torque / 5) * 5
Max_Torque = int(df_final['TShaft'].max())  
y_range = np.arange(Min_Torque, Max_Torque + Step_Torque, Step_Torque)
#------------------------------------------------------------------------------
xx, yy = np.meshgrid(x_range,y_range)

d = dict(tuple(df_final.groupby('Speed')))
last_values = {k: v.tail(1) for k, v in d.items()}
df_new = pd.concat([v for v in last_values.values()])
xm = pd.to_numeric(df_new ['Speed']).sort_values()
ym = pd.to_numeric(df_new ['TShaft']).sort_values(ascending=False)

interp_output = {}
interp_output2 = {}
for output in out_dataX:
    interp_output2[output] = griddata((df_final['Speed'],df_final['TShaft']), \
                            out_data[output], (xx, yy), method='linear')
    interp_output[output] = np.where(yy > (np.interp(xx, xm, ym)),\
                                     np.nan, interp_output2[output])
    interp_output[output].round(3)
    
# Reshape 2D arrays into 1D arrays
for key in interp_output:
    interp_output[key] = interp_output[key].flatten()

xx = xx.flatten()
yy = yy.flatten()

# Create a DataFrame from the reshaped dictionary
interp_output1 = pd.DataFrame.from_dict(interp_output)
interp_output1.insert(0, 'Speed', xx)
interp_output1.insert(1, 'TShaft', yy)

Data_Final = interp_output1.dropna()
Data_Final = Data_Final.sort_values(by=['Speed', 'TShaft'], \
                                    ascending=[True, True])

dfx = Data_Final
#______________________________________________________________________________

dfx1 = dfx.drop(dfx[dfx['temperature_PM']>= T_magnet].index)
dfx1 = dfx1.drop(dfx1[dfx1['temperature_winding'] >= T_Max_W].index)
Vcount = math.ceil(round(2*5/Step_Torque) / 1) * 1
dfx1 = dfx1[dfx1['Speed'].map(dfx1['Speed'].value_counts()) > Vcount]
#------------------------------------------------------------------------------
d = dict(tuple(dfx1.groupby('Speed')))
last_values = {k: v.tail(1) for k, v in d.items()}
df_n = pd.concat([v for v in last_values.values()])
x1 = df_n['Speed'].values

#df_speed_4000 = dfx[dfx['Speed'] == Rated_Speed]
#max_torque_at_4000 = df_speed_4000['TShaft'].max()
# y1 = np.where(x1 < Rated_Speed,max_torque_at_4000,max_torque_at_4000 *\
#                                                           Rated_Speed/ x1)
#y1 = max_torque_at_4000*Rated_Speed/ x1
#torque_limit_dict = dict(zip(x1, y1))
dfx = dfx[dfx['Speed'].isin(x1)]
#dfx = dfx[dfx.apply(lambda row: row['TShaft'] \
#                    <= torque_limit_dict[row['Speed']], axis=1)]
#------------------------------------------------------------------------------
#______________________________________________________________________________
  
Dcolumns = ['Speed [rpm]', 'TShaft [Nm]', 'Current-D [A]', 'Current-Q [A]',\
    'Line Voltage [rms]', 'Efficiency [%]', 'Inductance-D [uH]',\
    'Inductance-Q [uH]','Temp Winding Max [oC]', 'Temp PM Max [oC]']
DFy = pd.DataFrame(columns = Dcolumns)

DFy['Speed [rpm]'] = dfx['Speed'] 
DFy['TShaft [Nm]'] = dfx['TShaft']
DFy['Current-D [A]'] = dfx['Current']*np.sqrt(2)*np.sin(dfx['Gamma']/180*np.pi)
DFy['Current-Q [A]'] = dfx['Current']*np.sqrt(2)*np.cos(dfx['Gamma']/180*np.pi)
DFy['Line Voltage [rms]'] = dfx['VLL_rms']
DFy['Efficiency [%]'] = dfx['Efficiency']
DFy['Inductance-D [uH]'] = dfx['LD'] 
DFy['Inductance-Q [uH]'] = dfx['LQ'] 
DFy['Temp Winding Max [oC]'] = dfx['temperature_winding']
DFy['Temp PM Max [oC]'] = dfx['temperature_PM']

DFy = DFy.round(3)

DFy1 = DFy.query(
    '`Temp PM Max [oC]` < @T_magnet and `Temp Winding Max [oC]` < @T_Max_W')
DFy2 = DFy.query(
 'not (`Temp PM Max [oC]` < @T_magnet and `Temp Winding Max [oC]` < @T_Max_W)')
#
'''
DFy1.drop(columns=['Temp PM Max [oC]'], inplace=True)
DFy2.drop(columns=['Temp PM Max [oC]'], inplace=True)
'''
DFy1 = DFy1.copy()
DFy1.drop(columns=['Temp PM Max [oC]'], inplace=True)

DFy2 = DFy2.copy()
DFy2.drop(columns=['Temp PM Max [oC]'], inplace=True)
#______________________________________________________________________________    
         
File_Name = MotorName + str(VDC) + 'T0'+ str(T) 
#______________________________________________________________________________    
  
dfx = dfx.style.set_properties(**{
    'font-family': 'Aptos',
    'background-color': '#A0D2F8',
    'text-align':'center',
    'max-width':'50px',
    'font-size': '11pt',
})

dfx1 = dfx1.style.set_properties(**{
    'font-family': 'Aptos',
    'background-color': '#A0D2F8',
    'text-align':'center',
    'max-width':'50px',
    'font-size': '11pt',
})
#______________________________________________________________________________    

DFy1 = DFy1.style.set_properties(**{
    'font-family': 'Aptos',
    'background-color': '#A0D2F8',
    'text-align':'center',
    'max-width':'50px',
    'font-size': '11pt',
})

DFy2 = DFy2.style.set_properties(**{
    'font-family': 'Aptos',
    'background-color': '#A0D2F8',
    'text-align':'center',
    'max-width':'50px',
    'font-size': '11pt',
})
#______________________________________________________________________________    
#if Sanitised == 0: 
#writer = pd.ExcelWriter(Path + File_Name  +'ALL.xlsx',engine='xlsxwriter')
writer = pd.ExcelWriter(File_Name  +'ALL.xlsx',engine='xlsxwriter')
workbook = writer.book
dfx.to_excel(writer, sheet_name = File_Name + '_All'   , startrow=0, startcol=0, \
              index=False,header=True, freeze_panes=(1,1))
dfx1.to_excel(writer, sheet_name = File_Name  + '_Cont'  , startrow=0, startcol=0, \
              index=False,header=True, freeze_panes=(1,1))
    
workbook  = writer.book
worksheet1 = writer.sheets[File_Name + '_All']
worksheet2 = writer.sheets[File_Name  + '_Cont']

header_format = workbook.add_format({
    'bold': True,
    'text_wrap': True,
    'valign': 'center',
    'fg_color': '#029FCA',
    'border': 1})

for col_num, value in enumerate(dfx.columns.values):
    worksheet1.write(0, col_num, value, header_format)
for col_num, value in enumerate(dfx1.columns.values):
    worksheet2.write(0, col_num, value, header_format)

# Change the file attributes to read-only
#os.chmod(Path + File_Name  +'ALL.xlsx', S_IREAD|S_IRGRP|S_IROTH)

writer.close()
#______________________________________________________________________________    

#writer1 = pd.ExcelWriter(Path + File_Name  +'.xlsx',engine='xlsxwriter')
writer1 = pd.ExcelWriter( File_Name  +'.xlsx',engine='xlsxwriter')
workbook = writer1.book
DFy1.to_excel(writer1, sheet_name = File_Name + '_Cont',startrow=0,startcol=0,\
              index=False,header=True, freeze_panes=(1,1))
DFy2.to_excel(writer1, sheet_name = File_Name + '_Peak',startrow=0,startcol=0,\
              index=False,header=True, freeze_panes=(1,1))
    
workbook  = writer1.book
worksheet1 = writer1.sheets[File_Name + '_Cont']
worksheet2 = writer1.sheets[File_Name  + '_Peak']

header_format = workbook.add_format({
    'bold': True,
    'text_wrap': True,
    'valign': 'center',
    'fg_color': '#029FCA',
    'border': 1})

for col_num, value in enumerate(DFy1.columns.values):
    worksheet1.write(0, col_num, value, header_format)
for col_num, value in enumerate(DFy2.columns.values):
    worksheet2.write(0, col_num, value, header_format)

# Change the file attributes to read-only
#os.chmod(Path + File_Name  +'.xlsx', S_IREAD|S_IRGRP|S_IROTH)

writer1.close()
#______________________________________________________________________________