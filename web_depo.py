import streamlit as st
import pandas as pd
from datetime import datetime
import os
import qrcode
from io import BytesIO
from PIL import Image
import requests
import cv2
import numpy as np
import json
import gspread
from google.oauth2.service_account import Credentials

# --- GİZLİ KASA AYARLARI ---
try:
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    google_json_str = st.secrets["google_json"]
except:
    st.error("Gizli kasa (Secrets) ayarları bulunamadı!")
    st.stop()

# --- GOOGLE SHEETS BAĞLANTISI ---
scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds_dict = json.loads(google_json_str)
creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

try:
    sheet = client.open('MİDES - Temizlik Deposu')
except:
    st.error("Google Drive'da 'MİDES - Temizlik Deposu' adında bir tablo bulunamadı.")
    st.stop()

try:
    ws_malzemeler = sheet.worksheet("Malzemeler")
except:
    ws_malzemeler = sheet.add_worksheet(title="Malzemeler", rows="1000", cols="20")
    ws_malzemeler.append_row(["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok"])

try:
    ws_hareket = sheet.worksheet("Hareket_Gecmisi")
except:
    ws_hareket = sheet.add_worksheet(title="Hareket_Gecmisi", rows="1000", cols="10")
    ws_hareket.append_row(["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama"])

def log_kaydet(kullanici, islem_tipi, urun_adi, miktar, aciklama):
    zaman = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    mevcut_id = len(ws_hareket.get_all_values())
    ws_hareket.append_row([mevcut_id, zaman, kullanici, islem_tipi, urun_adi, miktar, aciklama])

def verileri_getir():
    kayitlar = ws_malzemeler.get_all_records()
    if not kayitlar:
        return pd.DataFrame(columns=["ID", "Stok No", "Ürün Adı", "Miktar", "Birim", "Eklenme Tarihi", "SKT", "Üretim Tarihi", "Giriş Tarihi", "Resim Yolu", "Kritik Stok"])
    df = pd.DataFrame(kayitlar)
    return df

def hareketleri_getir():
    kayitlar = ws_hareket.get_all_records()
    if not kayitlar:
        return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama"])
    return pd.DataFrame(kayitlar).sort_values(by="ID", ascending=False)

def df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sayfa1')
    return output.getvalue()

def qr_olustur(metin):
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(metin)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mesaj}
    try: requests.post(url, data=payload)
    except: pass

st.set_page_config(page_title="MİDES - Akıllı Depo", page_icon="📦", layout="wide")

if 'giris_yapildi' not in st.session_state:
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'rol': ""})

if not st.session_state['giris_yapildi']:
    st.markdown("<h1 style='text-align: center;'>🔐 Depo Yönetim Sistemi</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            secilen_rol = st.selectbox("Kullanıcı Tipi", ["Yönetici", "Personel"])
            girilen_sifre = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap", use_container_width=True):
                if secilen_rol == "Yönetici" and girilen_sifre == "Engin5307":
                    st.session_state.update({'giris_yapildi': True, 'kullanici': "Yönetici", 'rol': "admin"})
                    st.rerun()
                elif secilen_rol == "Personel" and girilen_sifre == "Depo5307":
                    st.session_state.update({'giris_yapildi': True, 'kullanici': "Personel", 'rol': "personel"})
                    st.rerun()
                else:
                    st.error("❌ Hatalı şifre!")
else:
    df = verileri_getir()
    bugun = datetime.now().date()
    
    c_ust1, c_ust2 = st.columns([4, 1])
    with c_ust1: st.title("📦 MİDES - Merkezi İkmal ve Depo Sistemi")
    with c_ust2:
        st.write(f"👤 *{st.session_state['kullanici']}*")
        if st.button("🚪 Çıkış Yap"):
            st.session_state['giris_yapildi'] = False
            st.rerun()

    sekme1, sekme2, sekme3, sekme6, sekme4, sekme5 = st.tabs(["📊 Özet", "➕ Ürün Ekle", "🔄 Güncelle", "⚡ Hızlı İşlem", "🪪 Ürün Kartı", "📝 Geçmiş"])

    with sekme1:
        st.markdown("### 📋 Depo Uyarıları")
        krt_sayisi = 0
        telegram_raporu = "⚠️ MİDES KRİTİK UYARI RAPORU ⚠️\n\n"
        
        for index, row in df.iterrows():
            urun_adi = str(row.get('Ürün Adı', 'Bilinmeyen Ürün')).strip()
            stok_no = str(row.get('Stok No', '-'))
            miktar_metni = str(row.get('Miktar', '0')).strip()
            birim = str(row.get('Birim', '')).strip()
            
            # 1. SKT Uyarıları (Parti Bazlı Detaylı)
            try:
                skt_metni = str(row.get('SKT', '')).strip()
                if skt_metni and skt_metni != "-" and skt_metni.lower() != "nan":
                    skt = datetime.strptime(skt_metni, '%Y-%m-%d').date()
                    kalan = (skt - bugun).days
                    uyari_baslik = f"{urun_adi} (Stok No: {stok_no} | {miktar_metni} {birim})"
                    
                    if kalan < 0:
                        st.error(f"❌ {uyari_baslik} - TARİHİ GEÇTİ! ({skt_metni})")
                        telegram_raporu += f"❌ {uyari_baslik} - TARİHİ GEÇTİ!\n"
                        krt_sayisi += 1
                    elif 0 <= kalan <= 30:
                        st.warning(f"⚠️ {uyari_baslik} - SKT'ye {kalan} gün kaldı! ({skt_metni})")
                        telegram_raporu += f"⚠️ {uyari_baslik} - {kalan} gün kaldı!\n"
                        krt_sayisi += 1
            except:
                pass
            
            # 2. Kritik Stok Uyarısı (Genel)
            try:
                kritik_metni = str(row.get('Kritik Stok', '10')).strip()
                if not miktar_metni or miktar_metni.lower() == "nan": miktar_metni = "0"
                if not kritik_metni or kritik_metni.lower() == "nan": kritik_metni = "10"
                
                miktar_val = float(miktar_metni)
                kritik_val = float(kritik_metni)
                
                if miktar_val <= kritik_val:
                    st.error(f"📉 STOK ALARMI: {urun_adi} (Stok No: {stok_no}) bitmek üzere! (Kalan: {int(miktar_val)} {birim})")
                    telegram_raporu += f"📉 ALARM: {urun_adi} (Stok No: {stok_no}) (Kalan: {int(miktar_val)} {birim})\n"
                    krt_sayisi += 1
            except:
                pass

        if krt_sayisi == 0:
            st.success("✅ Depo durumu çok iyi. Tarihi yaklaşan veya stoğu tükenen ürün yok.")
            telegram_raporu += "✅ Kritik ürün bulunmamaktadır. Depo güvende!"

        if st.button("📲 Telegram'a Rapor Gönder", type="primary"):
            telegram_mesaj_gonder(telegram_raporu)
            st.toast("✅ Gönderildi!")
            
        st.divider()
        
        # TOPLAM STOK GÖRÜNÜMÜ
        st.markdown("### 📦 Stok Numarasına Göre Genel Toplamlar")
        try:
            df['Miktar_Sayi'] = pd.to_numeric(df['Miktar'], errors='coerce').fillna(0)
            
            # Stok Numarasına göre grupla, isim ve birimin ilk girilenini baz al, miktarları topla
            toplam_stok_df = df.groupby('Stok No').agg({
                'Ürün Adı': 'first',
                'Miktar_Sayi': 'sum',
                'Birim': 'first'
            }).reset_index()
            
            toplam_stok_df.rename(columns={'Miktar_Sayi': 'Toplam Miktar'}, inplace=True)
            # Sütun sırasını düzenle
            toplam_stok_df = toplam_stok_df[['Stok No', 'Ürün Adı', 'Toplam Miktar', 'Birim']]
            
            st.dataframe(toplam_stok_df, use_container_width=True, hide_index=True)
        except:
            st.info("Toplamlar hesaplanırken bir hata oluştu. Miktar sütununda sadece rakam olduğundan emin olun.")

        st.markdown("### 🔍 Detaylı Parti (SKT ve Stok No) Listesi")
        gosterilecek_df = df.drop(columns=['Resim Yolu', 'Miktar_Sayi'], errors='ignore')
        st.dataframe(gosterilecek_df, use_container_width=True, hide_index=True)

    with sekme2:
        st.subheader("➕ Yeni Ürün Girişi")
        if st.session_state['rol'] == "personel":
            st.warning("Yetkiniz yok. Sadece yöneticiler yeni ürün ekleyebilir.")
        else:
            with st.form("ekleme_formu", clear_on_submit=True):
                c1, c2, c3, c4 = st.columns(4)
                stok = c1.text_input("Stok No")
                ad = c2.text_input("Ürün Adı")
                miktar = c3.number_input("Miktar", min_value=0, step=1)
                kritik = c4.number_input("Kritik Stok", value=10)
                birim = st.text_input("Birim (Adet, Kg vb.)")
                skt_t = st.date_input("⏳ SKT")
                if st.form_submit_button("🚀 Ekle"):
                    if ad and stok:
                        yeni_id = int(df['ID'].max()) + 1 if not df.empty else 1
                        eklenme_tarihi = datetime.now().strftime('%Y-%m-%d')
                        ws_malzemeler.append_row([yeni_id, stok, ad, miktar, birim, eklenme_tarihi, skt_t.strftime('%Y-%m-%d'), "-", "-", "", kritik])
                        log_kaydet(st.session_state['kullanici'], "YENİ ÜRÜN", ad, miktar, "Eklendi.")
                        st.success("✅ Ürün eklendi!")
                        st.rerun()

    with sekme3:
        st.subheader("🔄 Ürün Bilgilerini ve Stoğu Güncelle")
        if not df.empty:
            secili_guncelleme = st.selectbox("İşlem yapılacak ürünü seçin:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
            secili_id = int(secili_guncelleme.split(" - ")[0])
            urun = df[df['ID'] == secili_id].iloc[0]
            
            urun_miktar = int(float(str(urun.get('Miktar', '0')).strip() or '0'))
            urun_kritik = int(float(str(urun.get('Kritik Stok', '10')).strip() or '10'))
            
            st.info(f"📦 Mevcut Stok: *{urun_miktar} {urun['Birim']}*")
            
            with st.form("guncelleme_formu"):
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    yeni_stok_no = st.text_input("Stok No (Değiştirebilirsiniz):", value=str(urun.get('Stok No', '')))
                    kullanilan_miktar = st.number_input("➖ Depodan Çıkış (Kullanılan):", min_value=0, max_value=urun_miktar, step=1)
                    eklenen_miktar = st.number_input("➕ Depoya Giriş (Yeni Gelen):", min_value=0, step=1)
                    
                with col_g2:
                    try:
                        mevcut_skt = datetime.strptime(str(urun.get('SKT', '')).strip(), '%Y-%m-%d').date()
                    except:
                        mevcut_skt = bugun
                        
                    yeni_skt = st.date_input("Son Kullanma Tarihi (SKT):", value=mevcut_skt)
                    yeni_kritik = st.number_input("Kritik Stok Sınırı:", value=urun_kritik, min_value=1, step=1)
                
                if st.form_submit_button("💾 Değişiklikleri Kaydet", type="primary"):
                    yeni_toplam = urun_miktar - kullanilan_miktar + eklenen_miktar
                    satir_no = df[df['ID'] == secili_id].index[0] + 2
                    
                    ws_malzemeler.update_cell(satir_no, 2, yeni_stok_no) 
                    ws_malzemeler.update_cell(satir_no, 4, yeni_toplam)  
                    ws_malzemeler.update_cell(satir_no, 7, yeni_skt.strftime('%Y-%m-%d')) 
                    ws_malzemeler.update_cell(satir_no, 11, yeni_kritik) 
                    
                    if kullanilan_miktar > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", urun['Ürün Adı'], kullanilan_miktar, "")
                    if eklenen_miktar > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", urun['Ürün Adı'], eklenen_miktar, "")
                    
                    st.success("Ürün bilgileri başarıyla güncellendi!")
                    st.rerun()
                    
            st.divider()
            if st.session_state['rol'] == "admin":
                if st.button("🗑️ Seçili Ürünü Tamamen Sil"):
                    satir_no = df[df['ID'] == secili_id].index[0] + 2
                    ws_malzemeler.delete_rows(satir_no)
                    log_kaydet(st.session_state['kullanici'], "ÜRÜN SİLİNDİ", urun['Ürün Adı'], urun_miktar, "Silindi.")
                    st.success("Ürün silindi!")
                    st.rerun()

    with sekme6:
        st.subheader("⚡ Stok Numarası veya QR ile Hızlı İşlem")
        st.write("Ürünün QR kodunu kameraya okutun veya doğrudan Stok Numarasını elle yazın.")
        
        aranan_stok = st.text_input("🔍 Stok Numarasını Yazın ve Enter'a Basın:")
        resim = st.camera_input("📷 Veya Kamerayı Aç ve QR Okut")
        
        bulunan_stok_no = None
        
        if aranan_stok:
            bulunan_stok_no = str(aranan_stok).strip()
        elif resim is not None:
            img = Image.open(resim)
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            data, _, _ = cv2.QRCodeDetector().detectAndDecode(cv_img)
            if data:
                st.success("✅ QR Kod Okundu!")
                try:
                    bulunan_stok_no = next((s.split("Stok No:")[1].strip() for s in data.split('\n') if "Stok No:" in s), None)
                except:
                    st.error("QR kod formatı anlaşılamadı.")
            else:
                st.warning("QR kod algılanamadı.")
                
        if bulunan_stok_no:
            eslesen = df[df['Stok No'].astype(str).str.strip() == bulunan_stok_no]
            if not eslesen.empty:
                u_isim = eslesen.iloc[0]['Ürün Adı']
                u_id = eslesen.iloc[0]['ID']
                u_mik = int(float(str(eslesen.iloc[0]['Miktar']).strip() or '0'))
                u_resim = eslesen.iloc[0].get('Resim Yolu', '')
                
                st.info(f"📦 Bulunan Ürün: *{u_isim}* (Mevcut Stok: {u_mik})")
                
                # Ürün fotoğrafını bulup ekranda göster
                if pd.notna(u_resim) and str(u_resim).strip() not in ["", "-", "nan"]:
                    resim_tam_yol = os.path.join(RESIM_KLASORU, str(u_resim))
                    if os.path.exists(resim_tam_yol):
                        st.image(Image.open(resim_tam_yol), width=200)
                
                with st.form("hizli_islem_formu"):
                    col_q1, col_q2 = st.columns(2)
                    with col_q1:
                        miktar_dus = st.number_input("➖ Çıkarılacak Miktar:", min_value=0, max_value=u_mik, step=1)
                    with col_q2:
                        miktar_ekle = st.number_input("➕ Eklenecek Miktar:", min_value=0, step=1)
                        
                    if st.form_submit_button("💾 Güncelle", type="primary"):
                        if miktar_dus > 0 or miktar_ekle > 0:
                            yeni = u_mik - miktar_dus + miktar_ekle
                            satir_no = eslesen.index[0] + 2
                            ws_malzemeler.update_cell(satir_no, 4, yeni)
                            
                            if miktar_dus > 0: log_kaydet(st.session_state['kullanici'], "HIZLI ÇIKIŞ", u_isim, miktar_dus, f"Stok No: {bulunan_stok_no}")
                            if miktar_ekle > 0: log_kaydet(st.session_state['kullanici'], "HIZLI GİRİŞ", u_isim, miktar_ekle, f"Stok No: {bulunan_stok_no}")
                            
                            st.success("Stok başarıyla güncellendi!")
                            st.rerun()
                        else:
                            st.warning("Lütfen işlem yapmak için eklenecek veya çıkarılacak bir miktar girin.")
            else:
                st.error("❌ Bu stok numarasına ait ürün bulunamadı.")
                st.info("💡 Not: İleride tekrar deponuza gelecek ürünleri silmeyin, miktarlarını 0'a düşürün. Böylece bilgileri ve fotoğrafları kayıtlı kalır.")

    with sekme4:
        st.subheader("🪪 Ürün Tanıtım Kartı")
        if not df.empty:
            secilen = st.selectbox("Kartı Göster:", df['ID'].astype(str) + " - " + df['Ürün Adı'], key="qr_krt")
            urun_bilgisi = df[df['ID'] == int(secilen.split(" - ")[0])].iloc[0]
            qr_icerik = f"Ürün: {urun_bilgisi['Ürün Adı']}\nStok No: {urun_bilgisi['Stok No']}\nMiktar: {urun_bilgisi['Miktar']}\nSKT: {urun_bilgisi['SKT']}"
            st.image(qr_olustur(qr_icerik), caption="Bu Kodu Okutabilirsiniz")

    with sekme5:
        st.subheader("📝 Hareket Geçmişi")
        st.dataframe(hareketleri_getir(), use_container_width=True)
