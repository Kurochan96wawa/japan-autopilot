# -*- coding: utf-8 -*-
"""リードマグネットPDF生成（出発前チェックリスト＋2026年ファクト＋7日東京旅程＋日本語フレーズ）。
leadmagnet.py から import して使用。2026-07-16 に薄い1枚版から作り直し。"""
from __future__ import annotations
from .util import log


def build_pdf(path) -> bool:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                        Spacer, Table, TableStyle, KeepTogether, PageBreak, HRFlowable)
        from reportlab.lib.styles import ParagraphStyle
    except Exception as e:
        log.error("reportlab not available, skipping PDF: %s", e)
        return False
    try:
        import os as _os
        BASE, BOLD, DVBOX = "Helvetica", "Helvetica-Bold", None
        dv = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        dvb = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if _os.path.exists(dv):
            try:
                pdfmetrics.registerFont(TTFont("DV", dv))
                if _os.path.exists(dvb):
                    pdfmetrics.registerFont(TTFont("DVB", dvb)); BOLD = "DVB"
                else:
                    pdfmetrics.registerFont(TTFont("DVB", dv)); BOLD = "DVB"
                BASE, DVBOX = "DV", "DV"
            except Exception:
                pass
        CB = ('<font name="%s">☐</font>&nbsp;' % DVBOX) if DVBOX else "[ ]&nbsp;"
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5")); JPFONT = "HeiseiKakuGo-W5"; HAVE_JP = True
        except Exception:
            JPFONT = BASE; HAVE_JP = False

        ROSE = colors.HexColor("#d6336c"); ROSE_DARK = colors.HexColor("#a61e4d")
        PINK_BG = colors.HexColor("#fff0f5"); PINK_BD = colors.HexColor("#ffd0e0")
        INK = colors.HexColor("#2b2b2b"); GRAY = colors.HexColor("#6b7280")

        def S(n, **kw):
            b = dict(fontName=BASE, textColor=INK, fontSize=9.2, leading=13.2, spaceAfter=2)
            b.update(kw); return ParagraphStyle(n, **b)
        st_title = S("t", fontName=BOLD, fontSize=23, leading=25, textColor=colors.white)
        st_sub   = S("s", fontSize=10.5, leading=13, textColor=colors.HexColor("#ffe3ee"))
        st_intro = S("i", fontSize=9.6, leading=13.6, textColor=GRAY, spaceAfter=6)
        st_sec   = S("sec", fontName=BOLD, fontSize=12, leading=13, textColor=colors.white)
        st_item  = S("it", fontSize=9.2, leading=13.4, spaceAfter=1.5)
        st_factt = S("ft", fontName=BOLD, fontSize=9.8, leading=12.5, textColor=ROSE_DARK, spaceAfter=1)
        st_factb = S("fb", fontSize=8.8, leading=12, textColor=INK)
        st_note  = S("nt", fontSize=7.7, leading=9.5, textColor=GRAY)
        st_dayh  = S("dh", fontName=BOLD, fontSize=9.6, leading=12, textColor=ROSE_DARK, spaceBefore=3, spaceAfter=0.5)
        st_dayb  = S("db", fontSize=8.9, leading=12.2, textColor=INK, spaceAfter=2)
        st_h2    = S("h2", fontName=BOLD, fontSize=11, leading=13, textColor=ROSE_DARK, spaceBefore=4, spaceAfter=3)
        st_foot  = S("fo", fontSize=7.6, leading=10, textColor=GRAY)
        st_link  = S("lk", fontSize=8.9, leading=13, textColor=INK)

        def sec_header(txt):
            t = Table([[Paragraph(txt, st_sec)]], colWidths=[176*mm])
            t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),ROSE),
                ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
                ("TOPPADDING",(0,0),(-1,-1),4.5),("BOTTOMPADDING",(0,0),(-1,-1),4.5),
                ("ROUNDEDCORNERS",[3,3,3,3])])); return t
        def two_col(items):
            half=(len(items)+1)//2; left=items[:half]; right=items[half:]; data=[]
            for i in range(max(len(left),len(right))):
                l=Paragraph(CB+left[i],st_item) if i<len(left) else ""
                r=Paragraph(CB+right[i],st_item) if i<len(right) else ""
                data.append([l,r])
            t=Table(data,colWidths=[88*mm,88*mm])
            t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),6),
                ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)])); return t
        def onecol(items):
            data=[[Paragraph(CB+it,st_item)] for it in items]
            t=Table(data,colWidths=[176*mm])
            t.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
                ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)])); return t
        def fact_card(title,body,note):
            inner=[[Paragraph(title,st_factt)],[Paragraph(body,st_factb)],[Paragraph(note,st_note)]]
            t=Table(inner,colWidths=[84*mm])
            t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PINK_BG),("BOX",(0,0),(-1,-1),0.7,PINK_BD),
                ("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),
                ("TOPPADDING",(0,0),(0,0),6),("BOTTOMPADDING",(0,0),(-1,-1),1),
                ("TOPPADDING",(0,2),(0,2),2),("BOTTOMPADDING",(0,2),(0,2),6)])); return t
        def facts_grid(cards):
            rows=[]
            for i in range(0,len(cards),2):
                pr=cards[i:i+2]
                if len(pr)==1: pr.append("")
                rows.append(pr)
            t=Table(rows,colWidths=[88*mm,88*mm])
            t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                ("LEFTPADDING",(0,0),(0,-1),0),("RIGHTPADDING",(0,0),(0,-1),4),
                ("LEFTPADDING",(1,0),(1,-1),4),("RIGHTPADDING",(1,0),(1,-1),0),
                ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),6)])); return t

        doc=BaseDocTemplate(str(path),pagesize=A4,leftMargin=17*mm,rightMargin=17*mm,
            topMargin=16*mm,bottomMargin=14*mm,
            title="Japan With Kids - Family Trip Checklist & Planner (2026)",
            author="littletabi.com",subject="Free family travel guide")
        frame=Frame(doc.leftMargin,doc.bottomMargin,doc.width,doc.height,id="f")
        def footer(canvas,d):
            canvas.saveState(); canvas.setFillColor(GRAY); canvas.setFont(BASE,7.4)
            canvas.drawString(d.leftMargin,9*mm,"littletabi.com - honest, practical guides for families visiting Japan. Prices, hours and rules change; confirm on official sites.")
            canvas.drawRightString(d.leftMargin+d.width,9*mm,"Page %d"%d.page)
            canvas.setStrokeColor(PINK_BD); canvas.setLineWidth(0.6)
            canvas.line(d.leftMargin,11.5*mm,d.leftMargin+d.width,11.5*mm); canvas.restoreState()
        doc.addPageTemplates([PageTemplate(id="main",frames=[frame],onPage=footer)])
        story=[]
        mast=Table([[Paragraph("Japan With Kids",st_title)],
            [Paragraph("Family Trip Checklist &amp; Planner  ·  a free guide from littletabi.com  ·  2026",st_sub)]],colWidths=[176*mm])
        mast.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),ROSE),
            ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
            ("TOPPADDING",(0,0),(0,0),11),("BOTTOMPADDING",(0,0),(0,0),1),
            ("TOPPADDING",(0,1),(0,1),0),("BOTTOMPADDING",(0,1),(0,1),11),("ROUNDEDCORNERS",[5,5,5,5])]))
        story.append(mast); story.append(Spacer(1,6))
        story.append(Paragraph("Everything we wish we'd known before travelling around Japan with young kids - a print-friendly checklist, the facts that actually matter in 2026, and a gentle 7-day Tokyo plan. Tick the boxes as you pack.",st_intro))
        story.append(Spacer(1,4))
        story.append(sec_header("Documents &amp; money")); story.append(Spacer(1,3))
        story.append(two_col([
            "Passports valid 6+ months; check if your nationality needs a visa",
            "Print or screenshot hotel bookings, flights and pre-booked tickets",
            "Some yen cash for day one (small shops &amp; shrines are often cash-only)",
            "Travel / health insurance that covers your children",
            "A tap-card plan: Suica, PASMO or ICOCA (or Welcome Suica for visitors)",
            "A photo of each child + your hotel address, in case you get separated"]))
        story.append(Spacer(1,6)); story.append(sec_header("Health &amp; safety")); story.append(Spacer(1,3))
        story.append(two_col([
            "Regular medicines in original packaging + a small first-aid kit",
            "Your child's usual fever / pain medicine - brands differ in Japan",
            "Note the nearest clinic &amp; pharmacy to your hotel",
            "Save the emergency numbers: 119 (ambulance / fire), 110 (police)",
            "For allergies: a translated allergy card to show at restaurants",
            "A hat, sunscreen and hand sanitiser in your day bag"]))
        story.append(Spacer(1,6)); story.append(sec_header("Packing for kids")); story.append(Spacer(1,3))
        story.append(two_col([
            "A day or two of diapers / formula, then buy locally - it's everywhere",
            "A lightweight, foldable stroller or a carrier for crowded stations",
            "Plane snacks and something for the &#8216;are we there yet&#8217; moments",
            "Refillable water bottles and a change of clothes in the day bag",
            "Season-right layers (summers hot &amp; humid; winters cold but mild)",
            "A familiar comfort toy for naps and long train rides"]))
        story.append(Spacer(1,7)); story.append(sec_header("Getting around &amp; luggage")); story.append(Spacer(1,3))
        story.append(onecol([
            "Big suitcases on the Shinkansen: bags 160&#8211;250 cm (length+width+height) need a free advance &#8216;oversized baggage&#8217; seat reservation",
            "Consider luggage forwarding (takuhaibin) hotel-to-hotel, or day luggage storage - station coin lockers fill up fast, especially large ones",
            "Kids&#8217; train fares: children aged 6&#8211;11 pay about half; under 6 usually ride free (see the fact box overleaf)"]))
        story.append(Spacer(1,6)); story.append(sec_header("Tech &amp; connectivity")); story.append(Spacer(1,3))
        story.append(two_col([
            "Sort an eSIM or pocket Wi-Fi before you land (maps + translation)",
            "Download offline maps and a translation language pack",
            "Power bank for long park days",
            "The right plug: Japan is Type A, 100 V"]))
        story.append(PageBreak())
        story.append(Paragraph("Good-to-know facts for 2026",st_h2))
        story.append(Paragraph("We keep these on one page because they change and they trip families up. Checked against official sources on 2026-07-07 - always confirm before you go.",st_note))
        story.append(Spacer(1,5))
        story.append(facts_grid([
            fact_card("Disney rental strollers","At Tokyo Disneyland &amp; DisneySea, rental strollers are for children who can sit unassisted (about 7 months+), up to 100&nbsp;cm tall and up to 15&nbsp;kg.","Bring your own if your child is bigger. Confirm on the official Tokyo Disney Resort site."),
            fact_card("Kids&#8217; train fares (JR)","Children aged 6&#8211;11 pay half the adult fare (Green / sleeper tickets are full price). Under 6 ride free - up to two under-6s per paying adult in non-reserved seats.","Source: JR-Central. Confirm on the official site."),
            fact_card("Shinkansen with big suitcases","On the Tokaido / Sanyo / Kyushu Shinkansen, baggage of 160&#8211;250&nbsp;cm total (L+W+H) needs a free &#8216;oversized baggage&#8217; seat reservation. Over 250&nbsp;cm isn&#8217;t allowed.","Reserve when you book your seat. Confirm on the official site."),
            fact_card("Tax-free shopping","Spend at least 5,000 yen (pre-tax) at one store on the same day. From 1&nbsp;Nov&nbsp;2026, Japan moves to a refund method: pay the tax-included price and claim the refund at the airport.","Bring your passport. Confirm current rules on official sources.")]))
        story.append(Spacer(1,4))
        story.append(Paragraph("A gentle 7-day Tokyo plan (with young kids)",st_h2))
        story.append(Paragraph("One big thing a day, buffers for naps and meltdowns, and plenty of snack breaks. Pre-book anything with timed entry.",st_note))
        story.append(Spacer(1,4))
        for h,b in [
            ("Day 1 - Arrive &amp; settle","Land, pick up IC cards, check in, then a gentle neighbourhood stroll and a konbini (convenience-store) dinner. <b>Kid tip:</b> early night to beat jet lag - don&#8217;t overplan day one."),
            ("Day 2 - Asakusa &amp; the river","Senso-ji temple and snacks along Nakamise, then an easy Sumida River boat (stroller-friendly and very visual). <b>Rainy day:</b> Sumida Aquarium at Tokyo Skytree."),
            ("Day 3 - Ueno","Ueno Zoo and the wide park to run around; pick just one museum (the Nature &amp; Science museum is a hit). Leave a buffer for naps."),
            ("Day 4 - teamLab &amp; the bay","Book teamLab Planets tickets ahead. Afternoon around Odaiba / Miraikan. Keep it light after a big morning."),
            ("Day 5 - Tokyo Disneyland or DisneySea","One park, one day. Rent a stroller at the gate (up to 100&nbsp;cm / 15&nbsp;kg). Plan around a midday rest; pre-book any paid ride reservations in the official app."),
            ("Day 6 - Shibuya / Harajuku slow day","The Scramble Crossing, a themed cafe, gacha machines and Yoyogi Park. Short hops and lots of snack breaks."),
            ("Day 7 - Flex &amp; fly","A buffer morning, last-minute (tax-free) shopping, luggage forwarding or storage, and off to the airport early.")]:
            story.append(KeepTogether([Paragraph(h,st_dayh),Paragraph(b,st_dayb)]))
        story.append(Spacer(1,3))
        story.append(Paragraph("<b>Going beyond Tokyo?</b> Our full 10-day Tokyo&#8211;Kyoto&#8211;Osaka family itinerary is free on the site.",st_dayb))
        story.append(PageBreak())
        story.append(Paragraph("Handy references",st_h2)); story.append(Spacer(1,3))
        em=Table([[Paragraph("<b>In an emergency</b>&nbsp;&nbsp; Dial <b>119</b> for ambulance / fire and <b>110</b> for police - free from any phone, and you can ask for an English-speaking operator. Japan also has a free 24-hour visitor hotline run by JNTO (search &#8216;JNTO Japan Visitor Hotline&#8217;).",st_factb)]],colWidths=[176*mm])
        em.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PINK_BG),("BOX",(0,0),(-1,-1),0.7,PINK_BD),
            ("LEFTPADDING",(0,0),(-1,-1),9),("RIGHTPADDING",(0,0),(-1,-1),9),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
        story.append(em); story.append(Spacer(1,7))
        story.append(Paragraph("A few useful phrases",st_h2)); story.append(Spacer(1,2))
        hs=S("phh",fontName=BOLD,fontSize=8.6,leading=11,textColor=colors.white)
        hsj=ParagraphStyle("phhj",fontName=(JPFONT if HAVE_JP else BOLD),fontSize=9,leading=11,textColor=colors.white)
        es=S("phe",fontSize=8.8,leading=11.5); rs=S("phr",fontSize=8.8,leading=11.5,textColor=GRAY)
        js=ParagraphStyle("phj",fontName=(JPFONT if HAVE_JP else BASE),fontSize=9,leading=12,textColor=INK)
        prows=[[Paragraph("English",hs),Paragraph("Say it (romaji)",hs),Paragraph("日本語" if HAVE_JP else "Japanese",hsj)]]
        for e,r,j in [
            ("Does this contain [X]?","Kore ni [X] wa haitte imasu ka?","これに〇〇は入っていますか？"),
            ("My child has a food allergy.","Kodomo ni shokumotsu-arerugii ga arimasu.","子どもに食物アレルギーがあります。"),
            ("Where is the nearest toilet?","Ichiban chikai toire wa doko desu ka?","一番近いトイレはどこですか？"),
            ("Is there a nursing / baby room?","Jugyuushitsu wa arimasu ka?","授乳室はありますか？"),
            ("Help, please!","Tasukete kudasai!","助けてください！"),
            ("Thank you!","Arigatou gozaimasu!","ありがとうございます！")]:
            prows.append([Paragraph(e,es),Paragraph(r,rs),Paragraph(j if HAVE_JP else "-",js)])
        pt=Table(prows,colWidths=[62*mm,64*mm,50*mm])
        pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),ROSE),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PINK_BG]),
            ("BOX",(0,0),(-1,-1),0.7,PINK_BD),("INNERGRID",(0,0),(-1,-1),0.4,PINK_BD),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        story.append(pt); story.append(Spacer(1,8))
        story.append(Paragraph("Free guides to explore next",st_h2)); story.append(Spacer(1,2))
        lrows=[[Paragraph("&#8594; "+t,st_link),Paragraph('<font color="#a61e4d">%s</font>'%u,st_link)] for t,u in [
            ("Make a printable allergy card","littletabi.com/tools/allergy-card.html"),
            ("Full family packing list","littletabi.com/essential-packing-list-for-japan-with-kids-2026.html"),
            ("10-day Tokyo-Kyoto-Osaka itinerary","littletabi.com/japan-family-itinerary-tokyo-kyoto-osaka-with-young-children.html"),
            ("Best family hotels in Tokyo","littletabi.com/best-family-hotels-tokyo-connecting-rooms.html"),
            ("Family eSIMs compared","littletabi.com/japan-esim-for-families-compared.html"),
            ("Build a free trip plan","littletabi.com/plan.html")]]
        lt=Table(lrows,colWidths=[70*mm,106*mm])
        lt.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
            ("TOPPADDING",(0,0),(-1,-1),1.5),("BOTTOMPADDING",(0,0),(-1,-1),1.5),
            ("LINEBELOW",(0,0),(-1,-2),0.4,PINK_BD),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
        story.append(lt); story.append(Spacer(1,10))
        story.append(HRFlowable(width="100%",thickness=0.6,color=PINK_BD)); story.append(Spacer(1,4))
        story.append(Paragraph("Made with care by <b>littletabi.com</b> - honest, practical guides for families visiting Japan, written with AI and an automated quality process. We don&#8217;t take paid or sponsored stays; we recommend places on merit. Some links are affiliate links that may earn us a small commission at no extra cost to you. Prices, hours and rules change - please confirm details on official sites before you travel.  © 2026 littletabi.",st_foot))
        doc.build(story)
        return True
    except Exception as e:
        log.error("PDF build failed: %s", e)
        return False
