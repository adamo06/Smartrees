from Smartrees.get_dataFrame import SmarTrees
from Smartrees.evo_temp import Temporal
from Smartrees.ee_query import get_meta_data, cloud_out, mapper
import ee
import numpy as np
import pandas as pd
import geemap
import geehydro
import requests
""" This class is used to get the global dataframes from images of pos (base is Nice)
between the date_start and date_stop. The images are chosen at a base scale of 30
and only images with a cloud coverage inferior to perc (base 20) are kept
Unique_days is default to 1 and means you don't keep more than one image for each day
"""
""" minimum code for dict of NDVI and norm temp dataframes:
data_getter=Datas()
dict_of_df=data_getter.get_data_from_dates()
"""
""" MINIMUM CODE for dict of NDVI and norm temp dataframes  AND  working dataframes:
data_getter=Datas()
dict_of_df=data_getter.get_data_from_dates()
temp, div_temp, raw_diff_temp, ndvi, div_ndvi, raw_diff_ndvi = get_evols(self, dict_of_dfs)
"""
""" PLOTTING ONE DATAFRAME OF DICT OF DFS : example

img=dict_of_dfs['LANDSAT/LC08/C01/T1_TOA/LC08_198030_20200731']['NDVI']
img_arr=np.array(img).reshape((get_data.shapes[4][0],get_data.shapes[4][1]))
plt.imshow(img_arr)

"""


class Datas():
    """Used to generate a dictionnary of  dataframes referenced by the ee_image name's as the key
    It contains Temperature and NDVI"""
    def __init__(
        self,
        date_start='2020-07-31',  #Start for search of images.    MINIMUM VALUE IS 2013-07-31 , bugs observed below
        date_stop='2021-01-31',  #Stop date for the search of images
        pos=[7.25, 43.7
             ],  #Pos of images, if 0, will be calculated as mean of corners
        width=[0.1, 0.1],  # Width in longitude and lattitude of the AOI region
        perc=20,  # Maximum percentage of cloud coverage
        sea_filtering=1,  # Filtering sea pixels 1 , not 0
        scale=30,  # Scale of images
        Unique_days=1,  # Accounting for days that are present in double
        saving_files=False,
        return_stats=0  # return mean and std of temperature before normalization or not
    ):  # Do we save files in raw_data
        # Datas relevant variables

        self.date_start = date_start
        self.date_stop = date_stop
        self.perc = perc
        self.Unique_days = Unique_days

        # SmarTrees relevant variables
        self.sea_filtering_d = sea_filtering
        self.corner1 = [pos[0] + width[0] / 2, pos[1] + width[1] / 2]
        self.corner2 = [pos[0] - width[0] / 2, pos[1] - width[1] / 2]
        self.pos = pos
        self.width = width
        self.tronc = 'LANDSAT/LC08/C01/T1_TOA/LC08_'
        self.scale = 30
        self.aoi = self.get_aoi()
        if sea_filtering == 1:
            self.sea_pixel()
        else:
            self.sea_pixels = None
        self.saving_files = saving_files
        self.return_stats = return_stats

    def get_aoi(self):
        "Get The polygon region for ee as a Polygone"
        aoi = ee.Geometry.Polygon([[[self.corner1[0], self.corner1[1]],
                                    [self.corner1[0], self.corner2[1]],
                                    [self.corner2[0], self.corner2[1]],
                                    [self.corner2[0], self.corner1[1]]]], None,
                                  False)
        return aoi

    def get_list_from_dates(self):
        """ gets a dataframe of ee_Images of the position pos taken between date_start and date_stop """
        df_image_list = get_meta_data(self.date_start, self.date_stop,
                                      self.pos)

        # Creating features dict

        return df_image_list.sort_values('Date')

    def filter_list(self, df):
        """ Filtering the images in the list of images based on various arguments """

        # cloud coverage
        df_output = cloud_out(df, perc=20)

        # Keep less cloudy image of each day if Unique_days==1
        if self.Unique_days == 1:

            df_output_list = []
            for date in df_output['Date']:
                df_output_list.append(date)
            df_intermediary = df_output.copy()

            for date in df_output_list:

                if len(df_intermediary[df_intermediary['Date'] == date]) > 1:
                    indexes = df_intermediary[df_intermediary['Date'] ==
                                              date].index
                    best_index = indexes[0]
                    best_coverage = df_intermediary.loc[best_index]['Cloud']
                    for index in indexes:
                        if df_intermediary.loc[index]['Cloud'] < best_coverage:
                            best_index = index
                            best_coverage = df_intermediary.loc[best_index][
                                'Cloud']

                    for index in indexes:
                        if index != best_index:
                            df_intermediary.drop(index, inplace=True)
            df_output = df_intermediary
        if self.saving_files == 1:
            self.save_list_of_files(df_output)
        return df_output

    def get_data_from_list(self, df):
        """ Long function that outputs a dictionnary of dataframes containing NDVI and Temperature """
        print(
            f" the dataframe contains {df.shape[0]} lines. considering a mean treatment of 4s, it would take approximately {4.5*df.shape[0]/60} minutes"
        )
        output = {}
        i = 0
        for name in df['id']:
            if i % 10 == 0:
                print(f"file {i} / {df['id'].shape[0]}")

            data = SmarTrees(name,
                             scale=self.scale,
                             sea_pixels=self.sea_pixels,
                             pos=self.pos,
                             width=self.width,
                             sea_filtering=self.sea_filtering_d,
                             return_stats=self.return_stats)
            if self.return_stats == 0:
                output[name], self.shapes = data.z_temperature()
            else:
                output[name], self.shapes, meanT, std_T = data.z_temperature()
                index_id = self.df_features[self.df_features['id'] ==
                                            name].index
                self.df_features.loc[index_id, 'mean_T'] = meanT
                self.df_features.loc[index_id, 'std_T'] = std_T

            i += 1

        return output


#--------------------------------------------------------------------------------------------------

    def try_widths(self, df):
        try:
            dict_df = self.get_data_from_list(df)
        except AttributeError:
            print('width not suited, halving it')
            self.width = [self.width[0] * 0.75, self.width[1] * 0.75]
            dict_df = self.try_widths(df)
        return dict_df

    def get_data_from_dates(self):
        """ Produce dict of NDVI and Norm_temp dataframes with their names as keys"""
        df = self.get_list_from_dates()
        df = self.filter_list(df)

        self.list_of_eeimages = df.copy()
        self.df_features = df[['id']]

        self.df_features.loc[:, 'mean_T'] = np.nan
        self.df_features.loc[:, 'std_T'] = np.nan

        dict_df = self.try_widths(df)

        if self.return_stats == 1:
            self.add_weather_features()

        if self.saving_files == 1:
            print('saving dict of dfs')
            self.save_dataframes(dict_df)
            self.save_features_df(self.df_features)

        return dict_df

    def sea_pixel(self, Tlim=297.5, NDVIlim=0):
        """ Define Sea pixels ONCE AND FOR ALL and list in dataframe self.sea_pixel if pixels are earth 1 or sea 0
        based on Tlim and NDVIlim arguments"""

        #Creation du DF B4,B,B10 sur l'image de référence

        df_B4 = ee.Image(
            'LANDSAT/LC08/C01/T1_TOA/LC08_195030_20210729').select(['B4'])
        df_B5 = ee.Image(
            'LANDSAT/LC08/C01/T1_TOA/LC08_195030_20210729').select(['B5'])
        df_B10 = ee.Image(
            'LANDSAT/LC08/C01/T1_TOA/LC08_195030_20210729').select(['B10'])
        df_B4 = pd.DataFrame(np.concatenate(
            geemap.ee_to_numpy(df_B4, region=self.aoi)),
                             columns=['B4'])
        df_B5 = pd.DataFrame(np.concatenate(
            geemap.ee_to_numpy(df_B5, region=self.aoi)),
                             columns=['B5'])
        df_B10 = pd.DataFrame(np.concatenate(
            geemap.ee_to_numpy(df_B10, region=self.aoi)),
                              columns=['B10'])
        df = df_B4.join(df_B5).join(df_B10)

        # Conversion df b4,,b5,b10 en dataframe Temp, NDVI
        b4 = df['B4']
        b5 = df['B5']
        ndvi = (b5 - b4) / (b5 + b4)

        df1 = pd.DataFrame((ndvi), columns=[f'NDVI'])

        init_df = df[['B10']].join(df1)

        def filter_temp(x, lim=Tlim):
            if x < lim:
                return 0
            else:
                return 1

        def filter_NDVI(x, lim=NDVIlim):
            if x < lim:
                return 0
            else:
                return 1

        cleaned_col_NDVI = init_df['NDVI'].apply(lambda x: filter_NDVI(x))
        cleaned_col_temp = init_df['B10'].apply(lambda x: filter_temp(x))

        df_new = pd.DataFrame(cleaned_col_NDVI).join(
            pd.DataFrame(cleaned_col_temp))
        df_new['output'] = 2 * df_new['NDVI'] + df_new['B10']
        dict_output = {0: 0, 1: 0, 2: 0, 3: 1}
        df_final = df_new['output'].apply(lambda x: dict_output[x])
        df_final[df_final.index < len(df_final) / 3] = 1
        self.sea_pixels = pd.DataFrame(df_final)
        return None

    def save_list_of_files(self, df):
        """ Saves ee_image details dataframe as csv fils in raw_data"""
        df.to_csv(
            f'./../raw_data/list_of_images_perc_{self.perc}_scale_{self.scale}_pos_{self.pos}_{self.date_start}-{self.date_stop}.csv',
            index=False)
        return None

    def save_dataframes(self, dict_of_dfs):
        """ Saves NDVI and Norm_temp dataframes as csv fils in raw_data"""
        dict_to_write = dict_of_dfs[list(dict_of_dfs.keys())[0]]
        dict_to_write['ee_Image'] = list(dict_of_dfs.keys())[0][
            29:]  # le nom sans le tronc commun self.tronc
        dict_to_write.to_csv(
            f'./../raw_data/Regroupment_of_dataframes_perc_{self.perc}_scale_{self.scale}_pos_{self.pos}_{self.date_start}-{self.date_stop}.csv'
        )
        for name in list(dict_of_dfs.keys())[1:]:
            dict_to_write = dict_of_dfs[name]
            dict_to_write['ee_Image'] = name[29:]
            dict_to_write.to_csv(
                f'./../raw_data/Regroupment_of_dataframes_perc_{self.perc}_scale_{self.scale}_pos_{self.pos}_{self.date_start}-{self.date_stop}.csv',
                mode='a',
                header=False)
        return None

    def save_evol_dfs(self, temp, div_temp, raw_diff_temp, ndvi, div_ndvi,
                      raw_diff_ndvi, perc, scale, pos, date_start, date_stop):
        """ Saves working dataframes as csv fils in raw_data"""
        names = [
            'temp', 'div_temp', 'raw_diff_temp', 'ndvi', 'div_ndvi',
            'raw_diff_ndvi'
        ]
        for i, df in enumerate(
            [temp, div_temp, raw_diff_temp, ndvi, div_ndvi, raw_diff_ndvi]):
            df.to_csv(
                f'./../raw_data/DF_{names[i]}_perc_{perc}_scale_{scale}_pos_{pos}_{date_start}-{date_stop}.csv'
            )
        return None

    def save_features_df(self, df):
        """ Saves working dataframes as csv fils in raw_data"""
        df.to_csv(
            f'./../raw_data/DF_Features_perc_{self.perc}_scale_{self.scale}_pos_{self.pos}_{self.date_start}-{self.date_stop}.csv'
        )
        return None

    def get_evols(self, dict_of_dfs):
        """ Calls class Temporal to get working dataframes"""
        get_evo = Temporal(dict_of_dfs)

        temp, div_temp, raw_diff_temp, ndvi, div_ndvi, raw_diff_ndvi = get_evo.get_evo_allfeat(
        )
        if self.saving_files == 1:
            self.save_evol_dfs(temp, div_temp, raw_diff_temp, ndvi, div_ndvi,
                               raw_diff_ndvi, self.perc, self.scale, self.pos,
                               self.date_start, self.date_stop)
        return temp, div_temp, raw_diff_temp, ndvi, div_ndvi, raw_diff_ndvi

    def get_response(self, date_query, time_image):
        y = date_query[0:4]
        m = date_query[5:7]
        d = date_query[8:]
        url = f"https://www.metaweather.com/api/location/{self.woeid}/{y}/{m}/{d}/"

        response = requests.get(url).json()

        def time_dec(time):
            h = int(time[0:2])
            m = int(time[3:5])
            s = int(time[6:8])
            time_dec = h + m / 60 + s / 3600
            return time_dec

        temp_list = []
        for i in range(len(response)):
            date = response[i]['created'][0:10]
            if date == date_query:
                time = response[i]['created'][11:19]
                temp_list.append(time_dec(time))

        time_ref_dec = time_dec(time_image)

        temp_list = [abs(value - time_ref_dec) for value in temp_list]
        for i, time in enumerate(temp_list):
            if time == min(temp_list):
                weather_measurement = response[i]
        return weather_measurement

    def get_woeid(self):
        latt = self.pos[1]
        long = self.pos[0]
        url = f'https://www.metaweather.com/api/location/search/?lattlong={latt},{long}'
        response = requests.get(url).json()
        city = response[0]
        print(f"{city['title']}: {city['woeid']} ({city['latt_long']})")

        self.woeid = city['woeid']
        return None

    def create_weather_features(self):
        self.weather_features = [
            'weather_state_name', 'min_temp', 'max_temp', 'the_temp',
            'wind_speed', 'wind_direction', 'air_pressure', 'humidity',
            'visibility', 'predictability'
        ]
        self.df_features.loc[:, 'weather_state_name'] = np.nan
        self.df_features.loc[:, 'min_temp'] = np.nan
        self.df_features.loc[:, 'max_temp'] = np.nan
        self.df_features.loc[:, 'the_temp'] = np.nan
        self.df_features.loc[:, 'wind_speed'] = np.nan
        self.df_features.loc[:, 'wind_direction'] = np.nan
        self.df_features.loc[:, 'air_pressure'] = np.nan
        self.df_features.loc[:, 'humidity'] = np.nan
        self.df_features.loc[:, 'visibility'] = np.nan
        self.df_features.loc[:, 'predictability'] = np.nan
        return None

    def add_weather_features(self):
        self.create_weather_features()
        self.get_woeid()
        self.test1 = self.df_features.copy()
        for index in self.list_of_eeimages.index:

            time_image = self.list_of_eeimages.loc[index, 'Time']
            date_query = self.list_of_eeimages.loc[index, 'Date']
            weather_measurement = self.get_response(date_query, time_image)
            for name in self.weather_features:
                self.df_features.loc[index, name] = weather_measurement[name]

        return None
