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

st.set_page_config(page_title="MİDES - Akıllı Depo", page_icon="📦", layout="wide")

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
    kullanici_tablosu = client.open("MİDES - Kullanıcılar").get_worksheet(0)
    df_kullanicilar = pd.DataFrame(kullanici_tablosu.get_all_records())
except:
    st.error("Google Drive'da gerekli tablolar bulunamadı. 'MİDES - Kullanıcılar' ve 'MİDES - Gıda Deposu' tablolarını kontrol edin.")
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
    return pd.DataFrame(kayitlar)

def hareketleri_getir():
    kayitlar = ws_hareket.get_all_records()
    if not kayitlar:
        return pd.DataFrame(columns=["ID", "Tarih", "Kullanıcı", "İşlem", "Ürün Adı", "Miktar", "Açıklama"])
    return pd.DataFrame(kayitlar).sort_values(by="ID", ascending=False)

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

# --- YENİ OTURUM VE ŞİFRE YÖNETİMİ ---
if 'giris_yapildi' not in st.session_state:
    st.session_state.update({'giris_yapildi': False, 'kullanici': "", 'rol': "", 'sifre_degistirme_modu': False})

if st.session_state['sifre_degistirme_modu']:
    st.warning("⚠️ Şifrenizin kullanım süresi (30 gün) dolmuş veya değişiklik talep ettiniz. Lütfen yeni şifre belirleyin.")
    yeni_sifre = st.text_input("Yeni Şifre:", type="password")
    yeni_sifre_tekrar = st.text_input("Yeni Şifre (Tekrar):", type="password")
    
    if st.button("Şifreyi Güncelle"):
        if yeni_sifre == yeni_sifre_tekrar and len(yeni_sifre) >= 4:
            satir_no = df_kullanicilar[df_kullanicilar['Kullanıcı Adı'] == st.session_state['kullanici']].index[0] + 2
            bugun = datetime.today().strftime('%Y-%m-%d')
            kullanici_tablosu.update_cell(satir_no, 2, yeni_sifre)
            kullanici_tablosu.update_cell(satir_no, 3, bugun)
            st.success("Şifreniz güncellendi! Lütfen sayfayı yenileyerek yeni şifrenizle giriş yapın.")
            st.session_state['sifre_degistirme_modu'] = False
            st.session_state['giris_yapildi'] = False
            st.stop()
        else:
            st.error("Şifreler uyuşmuyor veya çok kısa (en az 4 karakter olmalı).")
    st.stop()

if not st.session_state['giris_yapildi']:
    st.markdown("<h1 style='text-align: center;'>🔐 Gıda Deposu Yönetim Sistemi</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            kadi_input = st.text_input("Kullanıcı Adı")
            sifre_input = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş Yap", use_container_width=True):
                kullanici = df_kullanicilar[(df_kullanicilar['Kullanıcı Adı'] == kadi_input) & (df_kullanicilar['Şifre'] == str(sifre_input))]
                
                if not kullanici.empty:
                    yetki = kullanici['Yetki'].values[0]
                    if yetki == "Temizlik" or yetki == "Yonetici":
                        st.session_state['kullanici'] = kadi_input
                        st.session_state['rol'] = "admin" if yetki == "Yonetici" else "personel"
                        
                        son_guncelleme = pd.to_datetime(kullanici['Son Güncelleme'].values[0], errors='coerce')
                        gecen_gun = (datetime.today() - son_guncelleme).days
                        
                        if gecen_gun >= 30:
                            st.session_state['sifre_degistirme_modu'] = True
                            st.rerun()
                        else:
                            st.session_state['giris_yapildi'] = True
                            st.rerun()
                    else:
                        st.error("❌ Bu depoya giriş yetkiniz bulunmamaktadır!")
                else:
                    st.error("❌ Kullanıcı adı veya şifre hatalı!")
else:
    df = verileri_getir()
    bugun = datetime.now().date()
    
    c_ust1, c_ust2 = st.columns([4, 1])
    with c_ust1: st.title("📦 MİDES - Merkezi İkmal ve Depo Sistemi")
    with c_ust2:
        st.write(f"👤 {st.session_state['kullanici']}")
        if st.button("🔄 Şifre Değiştir"):
            st.session_state['sifre_degistirme_modu'] = True
            st.rerun()
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
            except: pass
            
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
            except: pass

        if krt_sayisi == 0:
            st.success("✅ Depo durumu çok iyi. Tarihi yaklaşan veya stoğu tükenen ürün yok.")
            telegram_raporu += "✅ Kritik ürün bulunmamaktadır. Depo güvende!"

        if st.button("📲 Telegram'a Rapor Gönder", type="primary"):
            telegram_mesaj_gonder(telegram_raporu)
            st.toast("✅ Gönderildi!")
            
        st.divider()
        st.markdown("### 📦 Stok Numarasına Göre Genel Toplamlar")
        try:
            df['Miktar_Sayi'] = pd.to_numeric(df['Miktar'], errors='coerce').fillna(0)
            toplam_stok_df = df.groupby('Stok No').agg({'Ürün Adı': 'first', 'Miktar_Sayi': 'sum', 'Birim': 'first'}).reset_index()
            toplam_stok_df.rename(columns={'Miktar_Sayi': 'Toplam Miktar'}, inplace=True)
            toplam_stok_df = toplam_stok_df[['Stok No', 'Ürün Adı', 'Toplam Miktar', 'Birim']]
            st.dataframe(toplam_stok_df, use_container_width=True, hide_index=True)
        except: st.info("Toplamlar hesaplanırken hata oluştu.")

        st.markdown("### 🔍 Detaylı Parti Listesi")
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
                        ws_malzemeler.append_row([yeni_id, stok, ad, miktar, birim, datetime.now().strftime('%Y-%m-%d'), skt_t.strftime('%Y-%m-%d'), "-", "-", "", kritik])
                        log_kaydet(st.session_state['kullanici'], "YENİ ÜRÜN", ad, miktar, "Eklendi.")
                        st.success("✅ Ürün eklendi!")
                        st.rerun()

    with sekme3:
        st.subheader("🔄 Ürün Bilgilerini Güncelle")
        if not df.empty:
            secili_guncelleme = st.selectbox("Ürünü seçin:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
            secili_id = int(secili_guncelleme.split(" - ")[0])
            urun = df[df['ID'] == secili_id].iloc[0]
            urun_miktar = int(float(str(urun.get('Miktar', '0')).strip() or '0'))
            
            with st.form("guncelleme_formu"):
                c_g1, c_g2 = st.columns(2)
                with c_g1:
                    yeni_stok = st.text_input("Stok No:", value=str(urun.get('Stok No', '')))
                    cikis = st.number_input("➖ Çıkış:", min_value=0, max_value=urun_miktar, step=1)
                    giris = st.number_input("➕ Giriş:", min_value=0, step=1)
                with c_g2:
                    try: skt_val = datetime.strptime(str(urun.get('SKT', '')).strip(), '%Y-%m-%d').date()
                    except: skt_val = bugun
                    y_skt = st.date_input("SKT:", value=skt_val)
                    y_kritik = st.number_input("Kritik Sınır:", value=int(float(str(urun.get('Kritik Stok', '10')).strip() or '10')), step=1)
                
                if st.form_submit_button("💾 Kaydet", type="primary"):
                    satir = df[df['ID'] == secili_id].index[0] + 2
                    ws_malzemeler.update_cell(satir, 2, yeni_stok) 
                    ws_malzemeler.update_cell(satir, 4, urun_miktar - cikis + giris)  
                    ws_malzemeler.update_cell(satir, 7, y_skt.strftime('%Y-%m-%d')) 
                    ws_malzemeler.update_cell(satir, 11, y_kritik) 
                    
                    if cikis > 0: log_kaydet(st.session_state['kullanici'], "ÇIKIŞ", urun['Ürün Adı'], cikis, "")
                    if giris > 0: log_kaydet(st.session_state['kullanici'], "GİRİŞ", urun['Ürün Adı'], giris, "")
                    st.success("Güncellendi!")
                    st.rerun()

    with sekme6:
        st.subheader("⚡ Hızlı İşlem")
        aranan_stok = st.text_input("🔍 Stok Numarasını Yazın:")
        resim = st.camera_input("📷 Veya QR Okut")
        bulunan = str(aranan_stok).strip() if aranan_stok else None
        
        if resim:
            cv_img = cv2.cvtColor(np.array(Image.open(resim)), cv2.COLOR_RGB2BGR)
            data, _, _ = cv2.QRCodeDetector().detectAndDecode(cv_img)
            if data:
                try: bulunan = next((s.split("Stok No:")[1].strip() for s in data.split('\n') if "Stok No:" in s), None)
                except: pass
                
        if bulunan:
            eslesen = df[df['Stok No'].astype(str).str.strip() == bulunan]
            if not eslesen.empty:
                st.info(f"📦 Bulunan Ürün: {eslesen.iloc[0]['Ürün Adı']} (Mevcut: {eslesen.iloc[0]['Miktar']})")
                with st.form("hizli"):
                    m_dus = st.number_input("➖ Çıkar:", min_value=0, step=1)
                    m_ekle = st.number_input("➕ Ekle:", min_value=0, step=1)
                    if st.form_submit_button("💾 Güncelle", type="primary"):
                        if m_dus > 0 or m_ekle > 0:
                            ws_malzemeler.update_cell(eslesen.index[0] + 2, 4, int(eslesen.iloc[0]['Miktar']) - m_dus + m_ekle)
                            st.success("Stok güncellendi!")
                            st.rerun()
            else: st.error("❌ Ürün bulunamadı.")

    with sekme4:
        st.subheader("🪪 Ürün Tanıtım Kartı")
        if not df.empty:
            secilen = st.selectbox("Kartı Göster:", df['ID'].astype(str) + " - " + df['Ürün Adı'])
            ub = df[df['ID'] == int(secilen.split(" - ")[0])].iloc[0]
            st.image(qr_olustur(f"Ürün: {ub['Ürün Adı']}\nStok No: {ub['Stok No']}\nMiktar: {ub['Miktar']}\nSKT: {ub['SKT']}"), caption="QR Kod")

    with sekme5:
        st.subheader("📝 Hareket Geçmişi")
        st.dataframe(hareketleri_getir(), use_container_width=True)
