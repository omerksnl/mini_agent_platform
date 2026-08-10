# Mini Agent Platform - Stajyer Projesi

Mevcut ürünün öğretici amaçlı minyatür sürümü.

Bir LLM'in nasıl çağrıldığı, promptun davranışı nasıl belirlediği, agent döngüsünün nasıl işlediği, modelin tool'u neye göre seçtiği, konuşma hafızasının nasıl taşındığı. Kimlik doğrulama, veritabanı ve arayüz bu konuyu çalıştırabilmek için gereken iskelettir; puanı onlar getirmez.

## Kapsam

Kayıt/giriş (JWT), tenant bazlı veri izolasyonu, agent tanımlama,
agent ile sohbet, tool çağırma, Redis cache (opsiyonel), basit bir arayüz.

## Teknoloji

- Backend: Python 3.12, FastAPI, SQLAlchemy + Alembic, PostgreSQL, Redis
- Agent: LangChain + LangGraph
- Frontend: serbest. React, Vue, Svelte
- Paketleme: Docker + docker-compose (Faz 3)

## Mimari

```
Arayüz
    |  HTTP + JWT
    v
FastAPI (api katmanı)      -> doğrulama, yetki, tenant çözümleme
    v
Servis katmani (core)      -> iş kuralları, agent döngüsü
    |
    +--> LLM istemcisi
    +--> Tool executer
    +--> Redis (cache, opsiyonel)
    v
SQLAlchemy -> PostgreSQL
```

Kural: `api/` iş mantığı içermez, `core/` HTTP bilmez, veritabanı sorgusu
sadece servis katmanında yapılır.

## Cache (Redis)

Sık okunan, seyrek değişen veriler Redis'te tutulur. Kaynak her zaman
PostgreSQL'dir; Redis sadece hızlandırma katmanıdır, veri kaybı tolere
edilebilir olmalıdır.

## Agent altyapısı (LangChain / LangGraph)

Agent döngüsü.

| Parça | Kullanılan | İş |
|---|---|---|
| Agent | `create_agent` (langchain.agents) | Düşün-çağır-gözlemle döngüsünü hazır veren graph |
| Tool | `@tool` / `StructuredTool` | Python fonksiyonunu LLM'in çağırabileceği hale getirir |
| Hafıza | Short Term Memory | Sohbet geçmişini bir sonraki tura taşır |
| Sınırlama | `ToolCallLimitMiddleware`, recursion limit | Sonsuz tool döngüsünü engeller |

Veritabanındaki tool kaydı çalışma anında Pydantic argüman
şemasına ve oradan `StructuredTool`'a çevrilir. Yani tool'lar kodda sabit
değildir, kullanıcı ekledikçe agent'ın elindeki tool listesi büyür.

## Arayüz

Minimum şu işler yapılabilmeli: giriş, agent oluşturma (prompt + model + tool
seçimi), agent ile sohbet, tool ekleme.

## Öğrenme hedefleri

Proje sonunda şu sorulara kendi kodunuzu göstererek cevap verebilmelisiniz:

- System prompt ile user mesajı arasındaki fark nedir, prompt değişince
  davranış nasıl değişir
- Model tool'u neye bakarak seçiyor (isim ve açıklamanın etkisi)
- Function calling turu nasıl işliyor: model tool ister, sonuç geri verilir,
  model tekrar çağrılır
- Konuşma hafızası nasıl taşınır, context penceresi dolduğunda ne olur
- Aynı soruya farklı sıcaklık değerlerinde neden farklı yanıt gelir
- Model yanlış argüman ürettiğinde veya tool hata verdiğinde sistem ne yapmalı
- Token tüketimi nerede artar, maliyeti ne belirler

## Fazlar

Proje üç fazda ilerler. Bir faz bitmeden diğerine geçilmez; her fazın sonunda
çalışan bir demo olur.

### Faz 1 - İskelet

Uygulamanın taşıyıcı yapısı.

- Proje kurulumu, PostgreSQL bağlantısı, Alembic
- Kayıt, giriş, JWT, tenant bazlı izolasyon
- Agent CRUD (ad, sistem promptu, model, sıcaklık)
- Giriş ve agent yönetimi için basit arayüz


### Faz 2 - Agent

Agent altyapısı.

- LangChain/LangGraph ile chat: `create_agent`, sistem promptu, model seçimi
- Sohbet ve mesaj kaydı, short term memory
- Tool altyapısı: hazır sistem tool'ları + kullanıcı tanımlı HTTP tool
- Tool çağrı döngüsü, tur limiti
- Sohbet arayüzü, tool ekleme ekranı
- Redis cache (opsiyonel), hata yönetimi

### Faz 3 - DevOps

Uyuglamayı dockerize etme.

- Backend için `Dockerfile`, arayüz için ayrı `Dockerfile`
- `docker-compose.yml`: backend, frontend, postgres, redis
- Ayarlar `.env` üzerinden okunur, imaja gömülmez
- Migration konteyner başlarken çalışır
- README: kurulum, çalıştırma, ortam değişkenleri

## Kurallar

- Commit formatı: `type(scope): aciklama` (feat, fix, docs, test, chore)
- İş PR ile birleşir, en az bir kişi inceler
- Env değeri repoya commitlenmez
- Kodda ve arayüzde emoji kullanılmaz

## Dikkat edilecekler

- Tenant filtresi
- Yetki kontrolü backend'de yapılır
- İş mantığı endpoint içinde değil serviste durur
- Tool argümanları modelden gelir, doğrulamadan kullanmayın
- Veriyi güncelleyen yerde cache'i temizlemeyi unutmayın, yoksa eski agent
  promptu ile çalışırsınız
