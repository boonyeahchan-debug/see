import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
import matplotlib.pyplot as plt
import numpy as np
import io
import zipfile
import os
import time
import contextily as cx

# 1. Fungsi penukaran Decimal ke DMS (Degree, Minute, Second)
def format_to_dms(deg):
    d = int(deg)
    md = abs(deg - d) * 60
    m = int(md)
    sd = (md - m) * 60
    return f"{d}°{m:02d}'{sd:02.0f}\""

st.title("Paparan & Ekspot Polygon dari CSV")

# Upload fail CSV
uploaded_file = st.file_uploader("Upload fail CSV", type=["csv"])

if uploaded_file is not None:
    # Baca CSV
    df = pd.read_csv(uploaded_file)

    st.write("Data yang dimuat naik:")
    st.dataframe(df)

    # Pastikan kolum wujud
    if {"E", "N"}.issubset(df.columns):
        
        # --- SEKSYEN TETAPAN PETA & EPSG ---
        st.sidebar.subheader("Tetapan Peta")
        
        # Input kod EPSG
        epsg_code = st.sidebar.text_input("Kod EPSG (Cth: 4326, 3857, 3386)", value="4390")
        
        show_satellite = st.sidebar.checkbox("Buka Layer Satelit (On/Off)")
        
        # --- TAMBAHAN: SLIDER ZOOM KELUAR ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("Tetapan Paparan")
        # Slider untuk margin dalam meter (0 hingga 500 meter)
        zoom_margin = st.sidebar.slider("Zoom Keluar (Margin dalam Meter)", min_value=0, max_value=500, value=10, step=5)
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Tetapan Label")
        show_stn = st.sidebar.checkbox("Papar Label Stesen (STN)")
        show_labels = st.sidebar.checkbox("Papar Bearing & Jarak")
        show_area = st.sidebar.checkbox("Papar Label Luas")

        # --- PEMPROSESAN DATA GEOSPATIAL ---
        # Tukar kepada tuple koordinat
        coords = list(zip(df["E"], df["N"]))
        
        # Bina polygon menggunakan Shapely
        polygon = Polygon(coords)

        # Tukar ke GeoDataFrame dan tetapkan CRS berdasarkan input EPSG
        gdf = gpd.GeoDataFrame(index=[0], geometry=[polygon], crs=f"EPSG:{epsg_code}")
        
        # Kira Luas dan Centroid (dalam unit asal EPSG)
        area = gdf.geometry.area[0]
        centroid = gdf.geometry.centroid[0]

        # --- SEKSYEN EKSPOT DATA ---
        st.subheader("Ekspot Data")
        col1, col2 = st.columns(2)

        # A. Ekspot GeoJSON
        geojson_data = gdf.to_json()
        col1.download_button(
            label="Download GeoJSON",
            data=geojson_data,
            file_name="polygon.geojson",
            mime="application/json"
        )

        # B. Ekspot Shapefile
        with col2:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                shapefile_name = "temp_shapefile"
                gdf.to_file(f"{shapefile_name}.shp")
                time.sleep(1) 
                for ext in ["shp", "shx", "dbf", "prj"]:
                    filename = f"{shapefile_name}.{ext}"
                    if os.path.exists(filename):
                        zip_file.write(filename)
            
            st.download_button(
                label="Download Shapefile (.zip)",
                data=zip_buffer.getvalue(),
                file_name="polygon_shapefile.zip",
                mime="application/zip"
            )

        # --- SEKSYEN PLOT ---
        st.subheader("Visualisasi")
        fig, ax = plt.subplots(figsize=(10, 10))
        
        # Plot Polygon Utama
        gdf.plot(ax=ax, edgecolor="blue", facecolor="lightblue" if not show_satellite else "none", 
                 alpha=0.4, linewidth=2, zorder=5)
        
        # --- LOGIK LAYER SATELIT ---
        if show_satellite:
            try:
                # Tukar data ke Web Mercator (EPSG:3857) untuk satelit
                gdf_plot = gdf.to_crs(epsg=3857)
                
                # Plot halimunan untuk setkan extent peta
                gdf_plot.plot(ax=ax, alpha=0) 
                
                # Tambah basemap satelit
                cx.add_basemap(ax, source=cx.providers.Esri.WorldImagery)
                
            except Exception as e:
                st.error(f"Gagal memuatkan layer satelit: {e}")

        # --- LOGIK LABEL STESEN (STN) ---
        if show_stn:
            points = list(polygon.exterior.coords)
            for j, p in enumerate(points[:-1]):
                ax.text(p[0], p[1], f" STN {j+1}", fontsize=9, color='black', fontweight='bold', zorder=20)
                ax.scatter(p[0], p[1], color='black', s=20, zorder=5)
        else:
            points = list(polygon.exterior.coords)
            for p in points[:-1]:
                ax.scatter(p[0], p[1], color='black', s=20, zorder=5)

        # --- LOGIK LABEL BEARING & JARAK ---
        if show_labels:
            points = list(polygon.exterior.coords)
            for i in range(len(points) - 1):
                p1 = points[i]
                p2 = points[i+1]
                
                dist = np.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)
                
                angle_rad = np.arctan2(p2[0] - p1[0], p2[1] - p1[1])
                bearing_deg = np.degrees(angle_rad) % 360
                bearing_str = format_to_dms(bearing_deg)
                
                mid_x = (p1[0] + p2[0]) / 2
                mid_y = (p1[1] + p2[1]) / 2
                
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                line_angle_rad = np.arctan2(dy, dx)
                line_angle_deg = np.degrees(line_angle_rad)
                
                rotation = line_angle_deg
                if 90 < line_angle_deg <= 270 or -270 < line_angle_deg <= -90:
                    rotation = line_angle_deg + 180
                
                label_text = f"{dist:.2f}m\n{bearing_str}"
                ax.text(mid_x, mid_y, label_text, 
                        fontsize=10, color='red', fontweight='bold',
                        ha='center', va='center', 
                        rotation=rotation, rotation_mode='anchor', zorder=10)

        # --- PAPARKAN LABEL LUAS ---
        if show_area:
            ax.text(centroid.x, centroid.y, f"LUAS\n{area:.2f} m²", 
                    fontsize=12, color='darkblue', fontweight='bold',
                    ha='center', va='center', 
                    bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle='round,pad=0.5'),
                    zorder=15)

        # --- PERBAIKAN: HADKAN KAWASAN PLOT (LIMITS) DENGAN MARGIN ---
        bounds = gdf.total_bounds # [minx, miny, maxx, maxy]
        
        # Menggunakan nilai dari slider zoom_margin
        ax.set_xlim(bounds[0] - zoom_margin, bounds[2] + zoom_margin)
        ax.set_ylim(bounds[1] - zoom_margin, bounds[3] + zoom_margin)
        
        ax.set_title(f"Polygon: Visualisasi Data (EPSG:{epsg_code})")
        ax.set_xlabel("E (Eastings)")
        ax.set_ylabel("N (Northings)")
        ax.set_aspect('equal', adjustable='box') 

        st.pyplot(fig)
    else:
        st.error("Fail CSV mesti mengandungi lajur 'E' dan 'N'.")