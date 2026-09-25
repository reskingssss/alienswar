#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MavelyLink — translation resources.

An EXTERNAL resource file, so a wording fix needs no change to any logic
(spec 3). Four languages: English, Arabic, French, Spanish.

Adding a language means adding one dict below and one entry in LANGUAGES.
Any key missing from a translation falls back to English rather than
showing a blank or a raw key, so a half-finished translation can never
break the window.

Arabic is right-to-left; RTL is declared here and applied by the tool.
"""

# code -> (native label, is RTL)
LANGUAGES = [
    ("en", "English", False),
    ("ar", "العربية", True),
    ("es", "Español", False),
    ("fr", "Français", False),
]

RTL_LANGS = {"ar"}


def language_labels():
    return [(c, n) for c, n, _ in LANGUAGES]


def is_rtl(code):
    return code in RTL_LANGS


EN = {
    "timer.no_rules": "Connecting to MavelyLink to load the posting schedule...",
    "free.title": "Free version",
    "free.generic": "This option is not available in the Free version.",
    "free.feature": "{feature} is not available in the Free version.",
    "free.upgrade": "Upgrade",
    "free.ok": "OK",
    # ---- top bar / chrome -------------------------------------------
    "app.title": "Chrome Profile Generator",
    "nav.about": "About",
    "nav.upgrade": "Upgrade",
    "nav.my_plan": "My plan",
    "nav.register": "Register licence",
    "nav.language": "Language",
    "banner.isolated": "ISOLATED PROFILES:",
    "banner.isolated_text": "each profile is fully separate, with its own fingerprint and cookies",
    "plan.free": "Free plan",
    "plan.pro": "Pro plan",
    "plan.team": "Unlimited for Team plan",

    # ---- tabs ---------------------------------------------------------
    "tab.profiles": "Profiles",
    "tab.invite": "Invite",
    "tab.timer": "USA Timer",
    "tab.scripts": "User Scripts",

    # ---- profiles tab -------------------------------------------------
    "cfg.title": "Configuration",
    "cfg.name": "Name",
    "cfg.count": "Count",
    "cfg.generate_with": "Generate with",
    "cfg.needs_chrome": "(user scripts need Chrome)",
    "cfg.desktop_icon": "Desktop icon",
    "cfg.fingerprint": "Fingerprint",
    "cfg.lang_screen": "Language / Screen Size",
    "cfg.languages": "Languages",
    "cfg.screen_size": "Screen size",
    "cfg.all": "All",
    "cfg.none": "None",
    "cfg.invert": "Inv",
    "cfg.generate": "Generate New Profile",
    "profiles.title": "Browser Profiles",
    "profiles.open_at": "Open at",
    "profiles.save": "SAVE",
    "profiles.open_browser": "Open browser",
    "profiles.created": "Created",
    "profiles.language": "Language",
    "profiles.yes": "YES",
    "profiles.no": "NO",
    "fp.summary": "=== Fingerprint Summary ===",
    "fp.hint": "Generate a profile to see its details here.",
    "status.total": "Total profiles",
    "status.scripts_active": "user script(s) active",

    # ---- invite tab ---------------------------------------------------
    "invite.offer": "Earn an extra $15 or get a Pro License*",
    "invite.subtitle": "Invite 5 people",
    "invite.terms": "* See the referral terms",
    "invite.your_link": "Your invite link",
    "invite.copy": "Copy link",
    "invite.copied": "Copied!",
    "invite.copied_msg": "Invite link copied to the clipboard.",
    "invite.progress": "{count} of {total} referrals",
    "invite.explain": ("A referral counts when someone you invited buys a licence through your "
                       "link. Clicks, downloads and Free installs do not count."),
    "invite.refresh": "Refresh",
    "invite.need_email": ("Add your email address to get your personal invite link.\n"
                          "It is also where a reward would be sent."),
    "invite.get_link": "Get my invite link",
    "invite.checking": "Checking...",
    "invite.offline": "Offline - showing the last known numbers.",
    "invite.offline_nolink": "Offline - connect to get your invite link.",
    "invite.reward_done": "Reward granted: your Pro licence is active.",
    "invite.share": "Share your link. {n} more to go.",
    "invite.goal": "You have reached the goal.",

    # ---- registration -------------------------------------------------
    "reg.title": "Register licence",
    "reg.prompt": "Paste your licence key:",
    "reg.submit": "Register",
    "reg.cancel": "Cancel",

    # ---- USA timer tab ------------------------------------------------
    "timer.title": "US Multi-State Time Display",
    "timer.subtitle": "The best hours to post for a US audience, live in every state.",
    "timer.your_time": "Your local time",
    "timer.golden_hours": "Golden hours",
    "timer.day_ranking": "Best days",
    "timer.state": "State",
    "timer.time": "Time",
    "timer.status": "Status",
    "timer.legend": "Legend",
    "timer.next_golden": "Next golden hour",
    "timer.tomorrow": "Tomorrow",
    "timer.notify": "Notify me when a golden hour starts",
    "timer.golden_now": "GOLDEN NOW",
    "timer.good_now": "Good time",
    "timer.am": "AM",
    "timer.pm": "PM",
    "timer.weekend": "Weekend",
    "st.GOLD": "GOLD",
    "st.GOOD": "GOOD",
    "st.OK": "OK",
    "st.LOW": "LOW",
    "st.GOLD.help": "Best possible time",
    "st.GOOD.help": "Strong time",
    "st.OK.help": "Acceptable",
    "st.LOW.help": "Poor time",

    # days
    "day.0": "Monday", "day.1": "Tuesday", "day.2": "Wednesday", "day.3": "Thursday",
    "day.4": "Friday", "day.5": "Saturday", "day.6": "Sunday",

    # US states
    "state.Arkansas": "Arkansas", "state.New York": "New York", "state.Texas": "Texas",
    "state.Florida": "Florida", "state.California": "California", "state.Tennessee": "Tennessee",
    "state.Ohio": "Ohio", "state.Oklahoma": "Oklahoma", "state.Missouri": "Missouri",
    "state.Pennsylvania": "Pennsylvania", "state.Arizona": "Arizona",

    # tips
    "tip.morning": "School-run is over — peak scrolling time.",
    "tip.lunch": "Lunch break — the strongest engagement window of the day.",
    "tip.evening": "Evening wind-down — people are relaxing with their phones.",
    "tip.wednesday": "Wednesday is the single best day of the week.",
    "tip.weekend": "Weekends are quiet — engagement drops.",
    "tip.default": "Most of this audience is active midday and mid-evening.",

    # ---- v7.0.0: server-controlled Python tabs (host chrome only) -------
    # A remote tab module supplies its own text; these are only the words the
    # HOST draws around it - the state panels and the refresh control. They
    # live here so a future translation can cover them, and lookup() falls
    # back to English (then to the key) for any language that omits them, so
    # nothing here can break a window.
    "tabs.refresh": "Refresh tabs",
    "tabs.refresh_tip": "Reload the tabs defined on your dashboard",
    "tabs.loading": "Loading this tab from MavelyLink\u2026",
    "tabs.offline_title": "{tab} is not available offline",
    "tabs.locked_hint": "This feature requires {plan}.",
    "tabs.refreshed": "Tabs refreshed.",
    "tabs.refresh_failed": "Could not reach MavelyLink. Tabs are unchanged.",
}

AR = {
    "timer.no_rules": "جارٍ الاتصال بـ MavelyLink لتحميل جدول النشر...",
    "free.title": "النسخة المجانية",
    "free.generic": "هذا الخيار غير متاح في النسخة المجانية.",
    "free.feature": "{feature} غير متاح في النسخة المجانية.",
    "free.upgrade": "ترقية",
    "free.ok": "موافق",
    "app.title": "مولّد ملفات كروم",
    "nav.about": "حول", "nav.upgrade": "ترقية", "nav.my_plan": "خطتي",
    "nav.register": "تسجيل الرخصة", "nav.language": "اللغة",
    "banner.isolated": "ملفات معزولة:",
    "banner.isolated_text": "كل ملف منفصل تماماً، ببصمته وملفات تعريف الارتباط الخاصة به",
    "plan.free": "الخطة المجانية", "plan.pro": "خطة برو", "plan.team": "خطة غير محدودة للفرق",
    "tab.profiles": "الملفات", "tab.invite": "الدعوة", "tab.timer": "توقيت أمريكا",
    "tab.scripts": "السكربتات",
    "cfg.title": "الإعدادات", "cfg.name": "الاسم", "cfg.count": "العدد",
    "cfg.generate_with": "الإنشاء باستخدام", "cfg.needs_chrome": "(السكربتات تحتاج كروم)",
    "cfg.desktop_icon": "أيقونة سطح المكتب", "cfg.fingerprint": "البصمة",
    "cfg.lang_screen": "اللغة / حجم الشاشة", "cfg.languages": "اللغات",
    "cfg.screen_size": "حجم الشاشة", "cfg.all": "الكل", "cfg.none": "لا شيء",
    "cfg.invert": "عكس", "cfg.generate": "إنشاء ملف جديد",
    "profiles.title": "ملفات المتصفح", "profiles.open_at": "يفتح على",
    "profiles.save": "حفظ", "profiles.open_browser": "فتح المتصفح",
    "profiles.created": "أُنشئ", "profiles.language": "اللغة",
    "profiles.yes": "نعم", "profiles.no": "لا",
    "fp.summary": "=== ملخص البصمة ===",
    "fp.hint": "أنشئ ملفاً لعرض تفاصيله هنا.",
    "status.total": "إجمالي الملفات", "status.scripts_active": "سكربت نشط",
    "invite.offer": "اربح 15 دولاراً إضافية أو احصل على رخصة برو*",
    "invite.subtitle": "ادعُ 5 أشخاص", "invite.terms": "* شروط الإحالة",
    "invite.your_link": "رابط الدعوة الخاص بك", "invite.copy": "نسخ الرابط",
    "invite.copied": "تم النسخ!", "invite.copied_msg": "تم نسخ رابط الدعوة.",
    "invite.progress": "{count} من {total} إحالات",
    "invite.explain": ("تُحتسب الإحالة عندما يشتري شخص دعوته رخصةً عبر رابطك. "
                       "النقرات والتنزيلات والتثبيتات المجانية لا تُحتسب."),
    "invite.refresh": "تحديث",
    "invite.need_email": ("أضف بريدك الإلكتروني للحصول على رابط الدعوة الخاص بك.\n"
                          "وهو أيضاً المكان الذي تُرسل إليه المكافأة."),
    "invite.get_link": "احصل على رابط الدعوة", "invite.checking": "جارٍ التحقق...",
    "invite.offline": "غير متصل - تُعرض آخر أرقام معروفة.",
    "invite.offline_nolink": "غير متصل - اتصل للحصول على رابطك.",
    "invite.reward_done": "تم منح المكافأة: رخصة برو مفعّلة.",
    "invite.share": "شارك رابطك. بقي {n}.", "invite.goal": "لقد وصلت إلى الهدف.",
    "reg.title": "تسجيل الرخصة", "reg.prompt": "الصق مفتاح الرخصة:",
    "reg.submit": "تسجيل", "reg.cancel": "إلغاء",
    "timer.title": "توقيت الولايات الأمريكية",
    "timer.subtitle": "أفضل أوقات النشر لجمهور أمريكي، مباشرةً في كل ولاية.",
    "timer.your_time": "توقيتك المحلي", "timer.golden_hours": "الساعات الذهبية",
    "timer.day_ranking": "أفضل الأيام", "timer.state": "الولاية", "timer.time": "الوقت",
    "timer.status": "الحالة", "timer.legend": "المفتاح",
    "timer.next_golden": "الساعة الذهبية القادمة", "timer.tomorrow": "غداً",
    "timer.notify": "نبّهني عند بدء ساعة ذهبية",
    "timer.golden_now": "ساعة ذهبية الآن", "timer.good_now": "وقت جيد",
    "timer.am": "صباحاً", "timer.pm": "مساءً", "timer.weekend": "عطلة نهاية الأسبوع",
    "st.GOLD": "ذهبي", "st.GOOD": "جيد", "st.OK": "مقبول", "st.LOW": "ضعيف",
    "st.GOLD.help": "أفضل وقت ممكن", "st.GOOD.help": "وقت قوي",
    "st.OK.help": "مقبول", "st.LOW.help": "وقت ضعيف",
    "day.0": "الإثنين", "day.1": "الثلاثاء", "day.2": "الأربعاء", "day.3": "الخميس",
    "day.4": "الجمعة", "day.5": "السبت", "day.6": "الأحد",
    "state.Arkansas": "أركنساس", "state.New York": "نيويورك", "state.Texas": "تكساس",
    "state.Florida": "فلوريدا", "state.California": "كاليفورنيا", "state.Tennessee": "تينيسي",
    "state.Ohio": "أوهايو", "state.Oklahoma": "أوكلاهوما", "state.Missouri": "ميزوري",
    "state.Pennsylvania": "بنسلفانيا", "state.Arizona": "أريزونا",
    "tip.morning": "انتهى موعد المدرسة — ذروة التصفح.",
    "tip.lunch": "استراحة الغداء — أقوى نافذة تفاعل في اليوم.",
    "tip.evening": "هدوء المساء — الناس يسترخون مع هواتفهم.",
    "tip.wednesday": "الأربعاء هو أفضل يوم في الأسبوع.",
    "tip.weekend": "عطلة نهاية الأسبوع هادئة — التفاعل ينخفض.",
    "tip.default": "معظم هذا الجمهور نشط في منتصف النهار ومنتصف المساء.",
}

FR = {
    "timer.no_rules": "Connexion à MavelyLink pour charger le calendrier de publication...",
    "free.title": "Version gratuite",
    "free.generic": "Cette option n'est pas disponible dans la version gratuite.",
    "free.feature": "{feature} n'est pas disponible dans la version gratuite.",
    "free.upgrade": "Mettre à niveau",
    "free.ok": "OK",
    "app.title": "Générateur de profils Chrome",
    "nav.about": "À propos", "nav.upgrade": "Passer à la version supérieure",
    "nav.my_plan": "Mon forfait", "nav.register": "Enregistrer la licence",
    "nav.language": "Langue",
    "banner.isolated": "PROFILS ISOLÉS :",
    "banner.isolated_text": "chaque profil est totalement séparé, avec ses propres empreinte et cookies",
    "plan.free": "Forfait gratuit", "plan.pro": "Forfait Pro",
    "plan.team": "Forfait Illimité pour équipe",
    "tab.profiles": "Profils", "tab.invite": "Inviter", "tab.timer": "Horaires USA",
    "tab.scripts": "Scripts",
    "cfg.title": "Configuration", "cfg.name": "Nom", "cfg.count": "Nombre",
    "cfg.generate_with": "Générer avec", "cfg.needs_chrome": "(les scripts nécessitent Chrome)",
    "cfg.desktop_icon": "Icône sur le bureau", "cfg.fingerprint": "Empreinte",
    "cfg.lang_screen": "Langue / Taille d'écran", "cfg.languages": "Langues",
    "cfg.screen_size": "Taille d'écran", "cfg.all": "Tout", "cfg.none": "Aucun",
    "cfg.invert": "Inv", "cfg.generate": "Générer un nouveau profil",
    "profiles.title": "Profils du navigateur", "profiles.open_at": "Ouvrir sur",
    "profiles.save": "ENREGISTRER", "profiles.open_browser": "Ouvrir le navigateur",
    "profiles.created": "Créé", "profiles.language": "Langue",
    "profiles.yes": "OUI", "profiles.no": "NON",
    "fp.summary": "=== Résumé de l'empreinte ===",
    "fp.hint": "Générez un profil pour voir ses détails ici.",
    "status.total": "Total des profils", "status.scripts_active": "script(s) actif(s)",
    "invite.offer": "Gagnez 15 $ de plus ou obtenez une licence Pro*",
    "invite.subtitle": "Invitez 5 personnes", "invite.terms": "* Voir les conditions de parrainage",
    "invite.your_link": "Votre lien d'invitation", "invite.copy": "Copier le lien",
    "invite.copied": "Copié !", "invite.copied_msg": "Lien d'invitation copié.",
    "invite.progress": "{count} parrainages sur {total}",
    "invite.explain": ("Un parrainage compte lorsqu'une personne invitée achète une licence via "
                       "votre lien. Les clics, téléchargements et installations gratuites ne comptent pas."),
    "invite.refresh": "Actualiser",
    "invite.need_email": ("Ajoutez votre adresse e-mail pour obtenir votre lien d'invitation.\n"
                          "C'est aussi là que la récompense serait envoyée."),
    "invite.get_link": "Obtenir mon lien", "invite.checking": "Vérification...",
    "invite.offline": "Hors ligne - derniers chiffres connus.",
    "invite.offline_nolink": "Hors ligne - connectez-vous pour obtenir votre lien.",
    "invite.reward_done": "Récompense accordée : votre licence Pro est active.",
    "invite.share": "Partagez votre lien. Encore {n}.", "invite.goal": "Objectif atteint.",
    "reg.title": "Enregistrer la licence", "reg.prompt": "Collez votre clé de licence :",
    "reg.submit": "Enregistrer", "reg.cancel": "Annuler",
    "timer.title": "Horaires des États-Unis",
    "timer.subtitle": "Les meilleures heures pour publier vers un public américain, en direct.",
    "timer.your_time": "Votre heure locale", "timer.golden_hours": "Heures en or",
    "timer.day_ranking": "Meilleurs jours", "timer.state": "État", "timer.time": "Heure",
    "timer.status": "Statut", "timer.legend": "Légende",
    "timer.next_golden": "Prochaine heure en or", "timer.tomorrow": "Demain",
    "timer.notify": "M'avertir au début d'une heure en or",
    "timer.golden_now": "HEURE EN OR", "timer.good_now": "Bon moment",
    "timer.am": "AM", "timer.pm": "PM", "timer.weekend": "Week-end",
    "st.GOLD": "OR", "st.GOOD": "BON", "st.OK": "CORRECT", "st.LOW": "FAIBLE",
    "st.GOLD.help": "Le meilleur moment", "st.GOOD.help": "Très bon moment",
    "st.OK.help": "Acceptable", "st.LOW.help": "Mauvais moment",
    "day.0": "Lundi", "day.1": "Mardi", "day.2": "Mercredi", "day.3": "Jeudi",
    "day.4": "Vendredi", "day.5": "Samedi", "day.6": "Dimanche",
    "state.New York": "New York", "state.Texas": "Texas", "state.Florida": "Floride",
    "state.California": "Californie", "state.Pennsylvania": "Pennsylvanie",
    "state.Arkansas": "Arkansas", "state.Tennessee": "Tennessee", "state.Ohio": "Ohio",
    "state.Oklahoma": "Oklahoma", "state.Missouri": "Missouri", "state.Arizona": "Arizona",
    "tip.morning": "L'école a commencé — pic de consultation.",
    "tip.lunch": "Pause déjeuner — la meilleure fenêtre d'engagement.",
    "tip.evening": "Détente du soir — les gens se relaxent avec leur téléphone.",
    "tip.wednesday": "Le mercredi est le meilleur jour de la semaine.",
    "tip.weekend": "Le week-end est calme — l'engagement chute.",
    "tip.default": "Ce public est surtout actif en milieu de journée et en soirée.",
}

ES = {
    "timer.no_rules": "Conectando con MavelyLink para cargar el calendario de publicación...",
    "free.title": "Versión gratuita",
    "free.generic": "Esta opción no está disponible en la versión gratuita.",
    "free.feature": "{feature} no está disponible en la versión gratuita.",
    "free.upgrade": "Mejorar",
    "free.ok": "Aceptar",
    "app.title": "Generador de perfiles de Chrome",
    "nav.about": "Acerca de", "nav.upgrade": "Mejorar", "nav.my_plan": "Mi plan",
    "nav.register": "Registrar licencia", "nav.language": "Idioma",
    "banner.isolated": "PERFILES AISLADOS:",
    "banner.isolated_text": "cada perfil está totalmente separado, con su propia huella y cookies",
    "plan.free": "Plan gratuito", "plan.pro": "Plan Pro", "plan.team": "Plan Ilimitado para equipos",
    "tab.profiles": "Perfiles", "tab.invite": "Invitar", "tab.timer": "Horario EE. UU.",
    "tab.scripts": "Scripts",
    "cfg.title": "Configuración", "cfg.name": "Nombre", "cfg.count": "Cantidad",
    "cfg.generate_with": "Generar con", "cfg.needs_chrome": "(los scripts necesitan Chrome)",
    "cfg.desktop_icon": "Icono de escritorio", "cfg.fingerprint": "Huella digital",
    "cfg.lang_screen": "Idioma / Tamaño de pantalla", "cfg.languages": "Idiomas",
    "cfg.screen_size": "Tamaño de pantalla", "cfg.all": "Todo", "cfg.none": "Ninguno",
    "cfg.invert": "Inv", "cfg.generate": "Generar nuevo perfil",
    "profiles.title": "Perfiles del navegador", "profiles.open_at": "Abrir en",
    "profiles.save": "GUARDAR", "profiles.open_browser": "Abrir navegador",
    "profiles.created": "Creado", "profiles.language": "Idioma",
    "profiles.yes": "SÍ", "profiles.no": "NO",
    "fp.summary": "=== Resumen de la huella ===",
    "fp.hint": "Genera un perfil para ver sus detalles aquí.",
    "status.total": "Perfiles totales", "status.scripts_active": "script(s) activo(s)",
    "invite.offer": "Gana 15 $ extra u obtén una licencia Pro*",
    "invite.subtitle": "Invita a 5 personas", "invite.terms": "* Ver las condiciones",
    "invite.your_link": "Tu enlace de invitación", "invite.copy": "Copiar enlace",
    "invite.copied": "¡Copiado!", "invite.copied_msg": "Enlace de invitación copiado.",
    "invite.progress": "{count} de {total} referidos",
    "invite.explain": ("Un referido cuenta cuando alguien a quien invitaste compra una licencia "
                       "con tu enlace. Los clics, descargas e instalaciones gratuitas no cuentan."),
    "invite.refresh": "Actualizar",
    "invite.need_email": ("Añade tu correo electrónico para obtener tu enlace de invitación.\n"
                          "También es donde se enviaría la recompensa."),
    "invite.get_link": "Obtener mi enlace", "invite.checking": "Comprobando...",
    "invite.offline": "Sin conexión - últimos datos conocidos.",
    "invite.offline_nolink": "Sin conexión - conéctate para obtener tu enlace.",
    "invite.reward_done": "Recompensa concedida: tu licencia Pro está activa.",
    "invite.share": "Comparte tu enlace. Faltan {n}.", "invite.goal": "Has alcanzado el objetivo.",
    "reg.title": "Registrar licencia", "reg.prompt": "Pega tu clave de licencia:",
    "reg.submit": "Registrar", "reg.cancel": "Cancelar",
    "timer.title": "Horario de los Estados Unidos",
    "timer.subtitle": "Las mejores horas para publicar a un público estadounidense, en vivo.",
    "timer.your_time": "Tu hora local", "timer.golden_hours": "Horas doradas",
    "timer.day_ranking": "Mejores días", "timer.state": "Estado", "timer.time": "Hora",
    "timer.status": "Estado", "timer.legend": "Leyenda",
    "timer.next_golden": "Próxima hora dorada", "timer.tomorrow": "Mañana",
    "timer.notify": "Avisarme cuando empiece una hora dorada",
    "timer.golden_now": "HORA DORADA", "timer.good_now": "Buen momento",
    "timer.am": "AM", "timer.pm": "PM", "timer.weekend": "Fin de semana",
    "st.GOLD": "ORO", "st.GOOD": "BUENO", "st.OK": "ACEPTABLE", "st.LOW": "BAJO",
    "st.GOLD.help": "El mejor momento", "st.GOOD.help": "Muy buen momento",
    "st.OK.help": "Aceptable", "st.LOW.help": "Mal momento",
    "day.0": "Lunes", "day.1": "Martes", "day.2": "Miércoles", "day.3": "Jueves",
    "day.4": "Viernes", "day.5": "Sábado", "day.6": "Domingo",
    "state.New York": "Nueva York", "state.Texas": "Texas", "state.Florida": "Florida",
    "state.California": "California", "state.Pennsylvania": "Pensilvania",
    "state.Arkansas": "Arkansas", "state.Tennessee": "Tennessee", "state.Ohio": "Ohio",
    "state.Oklahoma": "Oklahoma", "state.Missouri": "Misuri", "state.Arizona": "Arizona",
    "tip.morning": "Ya empezó el colegio — pico de consultas.",
    "tip.lunch": "Pausa del mediodía — la mejor franja de interacción.",
    "tip.evening": "Calma de la tarde — la gente se relaja con el móvil.",
    "tip.wednesday": "El miércoles es el mejor día de la semana.",
    "tip.weekend": "El fin de semana es tranquilo — la interacción baja.",
    "tip.default": "Este público está activo sobre todo a mediodía y por la tarde.",
}

CATALOGUE = {"en": EN, "ar": AR, "fr": FR, "es": ES}


def lookup(code, key):
    """Translated string, falling back to English, then to the key itself."""
    table = CATALOGUE.get(code) or EN
    if key in table:
        return table[key]
    return EN.get(key, key)
