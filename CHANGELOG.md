# IT Aman v3.3 — Full Printers-Tools Merge

## ✅ اللي اتضاف من Printers-Tools v1.3

### إضافة طابعة شبكة
- زر "فحص الشبكة" في شاشة Setup
- TCP scan على 631/9100 + mDNS + HTTP probe لاكتشاف الموديل
- تحميل وتثبيت Kyocera kyodialog.deb تلقائياً لو مش موجود
- إعداد InputSlot=One + Duplex=None تلقائياً بعد التثبيت

### حذف طابعة
- زر "حذف طابعة" في Setup
- cancel + cupsdisable + lpadmin -x مع تأكيد

### الطابعة الحرارية — برندات
- X-Printer XP-80: تحميل binary → تشغيل installer → PPD → lpadmin
- SPRT 80mm: تحميل zip → install.sh → rastertoprinter filter → PPD (FullCut) → lpadmin

### إصلاح الطباعة العامة
- "إصلاح سريع لنظام الطباعة" في القائمة الرئيسية
- stop CUPS + rm /var/spool/cups/* + start CUPS

## ✅ ثوابت النظام (محتفظ بها)
- توقيع Ed25519 + SHA256 على كل تحديث
- Daemon/GUI منفصلين (Unix socket)
- Public key مدمج في الكود — private key عند المطور فقط
- Scan cache 30 ثانية

## طريقة النشر بعد أي تعديل
```
release.bat 3.3
```
