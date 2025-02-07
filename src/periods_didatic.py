#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Apr  4 17:56:36 2023

@author: daniloceano
"""
import glob
import matplotlib 

import xarray as xr
import pandas as pd
import numpy as np

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.dates as mdates

import cmocean.cm as cmo

from metpy.calc import vorticity
from metpy.units import units

from scipy.signal import savgol_filter 
from scipy.ndimage.measurements import label, find_objects

from sklearn.preprocessing import normalize   
from sklearn import preprocessing

import cartopy.crs as ccrs
import cartopy

def convert_lon(xr,LonIndexer):
    xr.coords[LonIndexer] = (xr.coords[LonIndexer] + 180) % 360 - 180
    xr = xr.sortby(xr[LonIndexer])
    return xr

def get_min_zeta(track, zeta850):
    
    min_zeta, times = [], []
    lats, lons = [], []
    for t in zeta850[TimeIndexer]:
        datestr = pd.to_datetime(t.values)
        
        if datestr in track.index:
            times.append(t.values)
            lat,lon = track.loc[datestr]
            lats.append(lat), lons.append(lon)
            min_zeta.append(float(zeta850.sel({TimeIndexer:t}
                    ).sel({LatIndexer:lat,LonIndexer:lon},method='nearest'))) 
            
    df = pd.DataFrame(min_zeta, index=times).rename(columns={0:'zeta'})
    df['lat'] = lats 
    df['lon'] = lons
    df.index.names = [TimeIndexer]
    
    return df  

def filter_var(variable):
    window_lenght = round(len(variable)/2)
    if (window_lenght % 2) == 0:
        window_lenght += 1
    return savgol_filter(variable, window_lenght, 3, mode="nearest")

def array_vorticity(df):
    
    da = df.to_xarray()
    
    # Filter vorticity twice
    zeta_fil = xr.DataArray(filter_var(da.zeta), coords={'time':df.index})
    da = da.assign(variables={'zeta_fil':zeta_fil})
    zeta_fil2 = xr.DataArray(filter_var(zeta_fil),
                                 coords={'time':df.index})
    da = da.assign(variables={'zeta_fil2':zeta_fil2})
    
    # derivatives of the double-filtered vorticity
    da = da.assign(variables={'dzfil2_dt':
                da.zeta_fil2.differentiate(TimeIndexer,datetime_unit='h')})
        
    da = da.assign(variables={'dzfil2_dt2':
                da.dzfil2_dt.differentiate(TimeIndexer,datetime_unit='h')})
        
    da = da.assign(variables={'dzfil2_dt3':
                da.dzfil2_dt2.differentiate(TimeIndexer,datetime_unit='h')})
        
    # filter derivatives
    da = da.assign(variables={'dz_dt_fil2':
        xr.DataArray(filter_var(da.dzfil2_dt), coords={'time':df.index})})
    da = da.assign(variables={'dz_dt2_fil2':
        xr.DataArray(filter_var(da.dzfil2_dt2), coords={'time':df.index})})
    da = da.assign(variables={'dz_dt3_fil2':
        xr.DataArray(filter_var(da.dzfil2_dt3), coords={'time':df.index})})

    return da

def get_peaks_valleys(function):
    maxs = function.where(function > function.quantile(0.75))
    mins = function.where(function < function.quantile(0.25))
    # get indices of continuous data
    labels_peak, num_features_peak = label(~np.isnan(maxs))
    labels_valley, num_features_valley = label(~np.isnan(mins))
    slices_peak = find_objects(labels_peak)
    slices_valley = find_objects(labels_valley)
    # Get continuous series for dz_dt3 values higher than the 0.85 quantile
    # and lower than the 0.15 quantile
    continuous_max_dz = [maxs[sl] for sl in slices_peak if sl is not None]
    continuous_min_dz = [mins[sl] for sl in slices_valley if sl is not None]
    # Now, get maximum and mininum values (peaks and valleys)
    peaks, valleys = [], []
    times_peaks, times_valleys = [], []
    for data_peak in continuous_max_dz:
        peaks.append(data_peak.max())
        times_peaks.append(data_peak.idxmax())
    for data_valley in continuous_min_dz:
        valleys.append(data_valley.min())
        times_valleys.append(data_valley.idxmin())
    peaks = [float(p.values) for p in peaks]
    times_peaks = [t.values for t in times_peaks]
    df_peaks = pd.Series(peaks,index=times_peaks)
    valleys = [float(v.values) for v in valleys]
    times_valleys = [t.values for t in times_valleys]
    df_valleys = pd.Series(valleys,index=times_valleys)
    return df_peaks, df_valleys

def filter_peaks_valleys(series):
    # Remove peaks and valleys that occured very close to each other
    min_time_diff = pd.Timedelta(days=1)
    
    valid_indices = [series.index[0]]
    for i in range(1, len(series)):
        if series.index[i] - series.index[i-1] > min_time_diff:
            valid_indices.append(series.index[i])
    return series.loc[valid_indices]
    

def plot_didatic(da, fname):

    colors = ['k', '#65a1e6', '#d62828', '#f7b538', '#9aa981',]
    
    z = da.zeta_fil2
    dz = da.dz_dt_fil2*50
    dz2 = da.dz_dt2_fil2*500
    dz3 = da.dz_dt3_fil2*5000
    
    plt.close('all')
    fig = plt.figure(figsize=(15, 15))
    gs = gridspec.GridSpec(3, 3)
    
# =============================================================================
#   First figure: all series
# =============================================================================
    ax = fig.add_subplot(gs[0, 0],frameon=True)
    
    ax.plot(da.time,dz3,c=colors[3], linewidth=0.75,
              label=r'$\frac{∂^{3}ζ}{∂t^{3}}$')
    ax.plot(da.time,dz2,c=colors[2], linewidth=0.75,
              label=r'$\frac{∂^{2}ζ}{∂t^{2}}$')
    ax.plot(da.time,dz,c=colors[1], linewidth=0.75,
             label=r'$\frac{∂ζ}{∂t}$')
    ax.plot(da.time,z,c=colors[0], linewidth=2, label='ζ')
    
    ax.set_title('Plot ζ and its derivatives ')
    ax.legend(loc='upper center', bbox_to_anchor=(1.67, 1.45),ncol=4,
              fontsize=16)
    
# =============================================================================
#   Get peaks and vallys of the derivatives
# =============================================================================
    ax2 = fig.add_subplot(gs[0, 1],frameon=True)

    c = 1
    for function in [dz, dz2, dz3]: 
        peaks, valleys = get_peaks_valleys(function)
            
        for i in range(len(peaks)):
            ax2.scatter(peaks.index[i],peaks[i],facecolor=colors[c],
                        edgecolor='k', linewidth=2, s=150)
        for i in range(len(valleys)):
            ax2.scatter(valleys.index[i],valleys[i],facecolor=colors[c],
                        linewidth=2, s=150)
        ax2.plot(function.time,function,c=colors[c], linewidth=1,
                  linestyle='-')
        c+=1
    
    ax2.plot(da.time,z,c=colors[0], linewidth=2)
    ax2.set_title('         Get peaks and valleys in derivatives')
    
# =============================================================================
#   Separete data between peaks and valleys of the third derivative
# =============================================================================
    ax3 = fig.add_subplot(gs[0, 2],frameon=True)
    
    c=1
    for function in [dz, dz2, dz3]:
        peaks, valleys = get_peaks_valleys(function)
        
        peaks_filtered = filter_peaks_valleys(peaks)
        valleys_filtered = filter_peaks_valleys(valleys)
        
        for tpeak in peaks_filtered.index:
            ax3.scatter(tpeak, z.where(z.time==tpeak).dropna(dim='time'),
                        c=colors[c], edgecolor='k', s=150)
        for tvalley in valleys_filtered.index:
            ax3.scatter(tvalley, z.where(z.time==tvalley).dropna(dim='time'),
                        c=colors[c], s=150)
        c+=1
        
    ax3.plot(da.time,z,c=colors[0], linewidth=2)
    ax3.set_title('Filter peaks closer than 1 day\n and transpose to ζ series')
        
# =============================================================================
#   Identify mature stages
# =============================================================================
    ax4 = fig.add_subplot(gs[1, 0],frameon=True)
    
    # Mature stage will be defined as all points between a consecutive
    # maximum and minimum of the third vorticity!
    dz3_peaks, dz3_valleys = get_peaks_valleys(dz3)
    dz3_peaks_filtered = filter_peaks_valleys(dz3_peaks)
    dz3_valleys_filtered = filter_peaks_valleys(dz3_valleys)
    z_dz3_peaks = z.sel(time=dz3_peaks_filtered.index)
    z_dz3_valleys = z.sel(time=dz3_valleys_filtered.index)
    
    peaks = dz3_peaks_filtered.replace(dz3_peaks_filtered.values,
                                       'peak')
    valleys = dz3_valleys_filtered.replace(dz3_valleys_filtered.values,
                                           'valley')
    dz3_peaks_valleys = pd.concat([peaks,valleys]).sort_index()
    
    dt = z.time[1] - z.time[0]
    dt = pd.Timedelta(dt.values)
    
    six_hours = pd.Timedelta('6H')
    
    mature = []
    for i in range(len(dz3_peaks_valleys[:-1])):
        if (dz3_peaks_valleys[i] == 'peak') and \
            (dz3_peaks_valleys[i+1] == 'valley') :
            mature.append(pd.date_range(dz3_peaks_valleys.index[i],
                        dz3_peaks_valleys.index[i+1],
                        freq=f'{int(dt.total_seconds() / 3600)} H'))
    
    
    ax4.plot(da.time,z,c=colors[0], linewidth=2)
    for series in mature:
        ax4.fill_betweenx((z.min(),z.max()), series[0], series[-1],  
                          facecolor=colors[3], alpha=0.6)
    ax4.scatter(z_dz3_peaks.time,z_dz3_peaks,facecolor=colors[3],
                edgecolor='k', s=150)
    ax4.scatter(z_dz3_valleys.time,z_dz3_valleys,facecolor=colors[3], s=150)
    
    ax4.set_title('Mature stage')
    
# =============================================================================
#   Identifying intensification and incipient stages stages
# =============================================================================
    ax5 = fig.add_subplot(gs[1, 1],frameon=True)
    
    dz2_peaks, dz2_valleys = get_peaks_valleys(dz2)
    z_dz2_peaks = z.sel(time=dz2_peaks.index)
    z_dz2_valleys = z.sel(time=dz2_valleys.index)
        
    # If thre is a minimum of the second derivative before the start of 
    # mature phase, the intensification starts there. Else, there is an
    # incipient stage
    intensification = []
    for series, i in zip(mature, range(len(mature))):
        mature_start = series[0] 
        mature_end = series[-1] 
        if i == 0:
            if dz2_valleys.index[i] < mature_start:
                intensification_start = dz2_valleys.index[i]
                incipient = pd.date_range(z.time[0].values,intensification_start-dt,
                                freq=f'{int(dt.total_seconds() / 3600)} H')
                # incipient = z.time.sel(time=slice(z.time[0],
                #                                   intensification_start-dt))
            else:
                intensification_start = (z.time[0]).values
                incipient = []
        else:
            if dz2_valleys.index[0] < mature[0][0]:
                intensification_start = dz2_valleys.index[i]
            else:
                intensification_start = dz2_valleys.index[i-1]
        intensification_end = mature_start-dt
        intensification.append(pd.date_range(intensification_start,
                        intensification_end, 
                        freq=f'{int(dt.total_seconds() / 3600)} H'))

    for series in intensification:
        ax5.fill_betweenx((z.min(),z.max()), series[0],
                      series[-1], facecolor=colors[2], alpha=0.6)
        
    ax5.scatter(z_dz3_peaks.time,z_dz3_peaks,facecolor=colors[3],
                edgecolor='k', s=150)
    ax5.scatter(z_dz2_peaks.time,z_dz2_peaks,facecolor=colors[2],
                edgecolor='k', s=150)
    ax5.scatter(z_dz2_valleys.time,z_dz2_valleys,facecolor=colors[2], s=150)
    
    ax5.plot(da.time,z,c=colors[0], linewidth=2)
    ax5.set_title('Intensification stage')
    
# =============================================================================
#   Plot incipient stage, if there's any
# =============================================================================
    ax6 = fig.add_subplot(gs[1, 2],frameon=True)
    ax6.scatter(z_dz2_peaks.time,z_dz2_peaks,facecolor=colors[2],
                edgecolor='k', s=150)
    ax6.scatter(z_dz2_valleys.time,z_dz2_valleys,facecolor=colors[2], s=150)
    if len(incipient) > 0:
        ax6.fill_betweenx((z.min(),z.max()), incipient[0],
                  incipient[-1], facecolor=colors[1], alpha=0.6)
    ax6.plot(da.time,z,c=colors[0], linewidth=2)
    ax6.set_title('Incipient stage')

# =============================================================================
#   Get decaying stages
# =============================================================================
    ax7 = fig.add_subplot(gs[2, 0],frameon=True)
    decaying = []
    
    if len(mature) == 1:
        decaying_start = mature[0][-1] + dt
        decaying_end = z.time[-1].values
        decaying.append(pd.date_range(decaying_start, decaying_end, 
                        freq=f'{int(dt.total_seconds() / 3600)} H'))
        
    else:
        for series, i in zip(mature, range(len(mature))):
            mature_start = series[0]
            mature_end = series[-1]
            sliced_z = z.sel(time=slice(mature_end, z.time.max()))
            decaying_end = dz2_valleys[
                dz2_valleys.index >= sliced_z.time.min().values].index.min()
            if pd.isnull(decaying_end):
                decaying_end = z.time[-1].values            
            decaying_start = mature_end+dt
            decaying.append(pd.date_range(decaying_start, decaying_end, 
                            freq=f'{int(dt.total_seconds() / 3600)} H'))
        
    for series in decaying:
        if len(series) > 0:
            ax7.fill_betweenx((z.min(),z.max()), series[0], series[-1],  
                              facecolor=colors[4], alpha=0.6)
    ax7.scatter(z_dz2_peaks.time,z_dz2_peaks,facecolor=colors[2],
                edgecolor='k', s=150)
    ax7.scatter(z_dz2_valleys.time,z_dz2_valleys,facecolor=colors[2], s=150) 
    ax7.scatter(z_dz3_valleys.time,z_dz3_valleys,facecolor=colors[3], s=150)
        
    ax7.plot(da.time,z,c=colors[0], linewidth=2)
    ax7.set_title('Decaying stage')
    
# =============================================================================
#   Plot everything together
# =============================================================================
    ax8 = fig.add_subplot(gs[2, 1:3],frameon=True)
    
    phases = {}
    for phase, key in zip([[incipient], intensification, mature, decaying],
                    ['incipient', 'intensification', 'mature', 'decaying']):
        tmp = []
        for period in phase:
            if len(period) > 0:
                tmp.append(pd.date_range(
                    period[0]-six_hours, period[-1]+six_hours,
                              freq=f'{int(dt.total_seconds() / 3600)} H'))
        phases[key] = tmp
        
    for phase, c in zip(phases.keys(),
                          ['#65a1e6','#d62828','#f7b538','#9aa981']):
        for series in phases[phase]:
            if len(series) > 0:
                ax8.fill_betweenx((z.min(),z.max()), series[0],series[-1],  
                                  facecolor=c, alpha=0.6)
    
    ax8.plot(da.time,z,c=colors[0], linewidth=2)
    ax8.set_title('Add overlaps for six hours between periods as confidence interval')
    
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%b-%d'))
    plt.gca().xaxis.set_major_locator(mdates.DayLocator())
    plt.gcf().autofmt_xdate()

    outname = '../vorticity_analysis/didatic/'+fname
    outname+='.png'
    plt.savefig(outname,dpi=500)
    print(outname,'saved')
  
data_dir = '../met_data/ERA5/DATA/'
track_dir = '../tracks_LEC-format/intense/'
varlist = '../fvars/fvars_ERA5-cdsapi'

dfVars = pd.read_csv(varlist,sep= ';',index_col=0,header=0)
LonIndexer = dfVars.loc['Longitude']['Variable']
LatIndexer = dfVars.loc['Latitude']['Variable']
TimeIndexer = dfVars.loc['Time']['Variable']
LevelIndexer = dfVars.loc['Vertical Level']['Variable']    

for testfile in glob.glob(data_dir+'/*'):   
        
    fname = testfile.split('/')[-1].split('.nc')[0] 
    id_cyclone = fname.split('_')[0]
    track_file = track_dir+'track_'+id_cyclone
    print('Cyclone ID:',id_cyclone)
    print('Track file:',track_file)  
                    
    da = convert_lon(xr.open_dataset(testfile),LonIndexer)
    da850 = da.sel({LevelIndexer:850})
    u850 = da850[dfVars.loc['Eastward Wind Component']['Variable']] * units('m/s')
    v850 = da850[dfVars.loc['Northward Wind Component']['Variable']] * units('m/s')
    zeta850 = vorticity(u850,v850)
    
    track = pd.read_csv(track_file, parse_dates=[0],delimiter=';',index_col=TimeIndexer)

    df = get_min_zeta(track, zeta850) 
    
    da = array_vorticity(df)
    
    plot_didatic(da, fname)