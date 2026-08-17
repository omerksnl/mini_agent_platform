param([string]$OutputPath = (Join-Path $PSScriptRoot "..\activity_library.md"))

$activities = @'
Name|Category|Setting|Intensity|Duration|Equipment|Weather|Group|Cost|Why
Half-Court Basketball|Basketball|Outdoor|High|45-90 min|Ball and court shoes|Dry and mild|3-8 people|Free-Low|Fast team play with less running than a full court
Full-Court Basketball|Basketball|Indoor or outdoor|High|60-120 min|Ball and court shoes|Any indoors, dry outdoors|10 people|Low|Competitive team play and cardio
Basketball Shooting Practice|Basketball|Indoor or outdoor|Moderate|30-60 min|Ball and hoop|Any indoors, dry outdoors|Solo or pair|Free-Low|Relaxed skill practice with measurable goals
Three-on-Three Basketball|Basketball|Indoor or outdoor|High|45-90 min|Ball and one hoop|Any indoors, dry outdoors|6 people|Low|Social and tactical small-team basketball
Basketball HORSE Game|Basketball game|Indoor or outdoor|Low-Moderate|30-60 min|Ball and hoop|Any indoors, dry outdoors|2-5 people|Free-Low|Creative shooting competition without a full match
Casual Volleyball|Volleyball|Indoor or outdoor|Moderate|45-90 min|Ball and net|Any indoors, mild outdoors|6-12 people|Low|Social team sport with adjustable intensity
Beach Volleyball|Volleyball|Beach|High|45-90 min|Ball and net|Warm, dry, low wind|4-8 people|Low|Combines the sea, sand, and team play
Volleyball Passing Practice|Volleyball|Indoor or outdoor|Low-Moderate|25-50 min|Ball|Any indoors, dry outdoors|2-4 people|Free-Low|Simple cooperative practice before a match
Badminton Match|Badminton|Indoor or outdoor|Moderate-High|30-75 min|Rackets and shuttlecock|Low wind outdoors|2-4 people|Low-Medium|Quick racket sport that works for pairs
Badminton Rally Challenge|Badminton|Indoor or outdoor|Moderate|20-45 min|Rackets and shuttlecock|Low wind outdoors|2 people|Low|Cooperative challenge focused on keeping the rally alive
Table Tennis Session|Racket sport|Indoor|Moderate|30-75 min|Table, paddles, ball|Any|2-4 people|Low-Medium|Fast reactions with low travel and weather dependency
Swimming at a Public Beach|Sea and swimming|Outdoor|Moderate|60-180 min|Swimwear, towel, water|Warm, calm, supervised|Solo with supervision or group|Free-Low|Direct match for enjoying the sea
Morning Sea Swim|Sea and swimming|Outdoor|Moderate|30-75 min|Swimwear, towel|Warm, calm morning|Group preferred|Free|Quieter water and a refreshing start
Sunset Beach Visit|Sea and relaxation|Outdoor|Low|60-150 min|Towel or chair|Dry and mild|Solo or group|Free-Low|Combines scenery, rest, and photography
Beach Day with Games|Sea and social|Outdoor|Low-Moderate|3-6 hours|Towel, food, ball or cards|Warm and dry|Group|Low-Medium|Mixes swimming, picnic, cards, and light sports
Coastal Walk|Walking and scenery|Outdoor|Low-Moderate|45-120 min|Comfortable shoes|Dry, mild, low wind|Solo or group|Free|Sea views with an easy walking plan
Snorkeling Introduction|Sea exploration|Outdoor|Moderate|45-90 min|Mask, snorkel, fins optional|Clear, calm, supervised|Pair or group|Low-Medium|Adds exploration and photography-like observation to swimming
Kayak Coastal Tour|Water activity|Outdoor|Moderate|1-3 hours|Kayak, paddle, life jacket|Calm water and low wind|Group|Medium|Scenic exploration from the water
Island or Bay Day Trip|Sea travel|Outdoor|Low-Moderate|Half or full day|Transport, water, swim gear|Stable weather|Group|Medium|Combines travel, swimming, landscapes, and local discovery
Lakeside Picnic|Picnic and nature|Outdoor|Low|2-4 hours|Food, blanket, water|Dry and mild|Group|Low|Relaxed food and conversation beside nature
Forest Picnic|Picnic and nature|Outdoor|Low|2-4 hours|Food, blanket, waste bags|Dry and mild|Group|Low|Quiet shade, nature, and a social meal
Sunset Picnic|Picnic and scenery|Outdoor|Low|90-180 min|Food, blanket, lighting|Dry and mild|Pair or group|Low|Scenic rest with photography opportunities
Picnic with Card Games|Picnic and games|Outdoor|Low|2-4 hours|Food, blanket, cards|Dry and calm|Group|Low|Combines two stated interests in one plan
Picnic with Volleyball|Picnic and sport|Outdoor|Moderate|2-5 hours|Food, blanket, volleyball|Dry and mild|Group|Low|Alternates relaxed social time and team sport
Easy Nature Trail|Nature hiking|Outdoor|Low-Moderate|60-150 min|Walking shoes, water|Dry and daylight|Solo or group|Free-Low|Accessible nature walk with time for scenery
Forest Hike|Nature hiking|Outdoor|Moderate|2-4 hours|Trail shoes, water, map|Dry and stable|Group preferred|Low|Immersive nature and longer exploration
Waterfall Hike|Nature hiking|Outdoor|Moderate|2-5 hours|Trail shoes, water|Dry trail conditions|Group preferred|Low-Medium|A scenic destination gives the hike a clear goal
Coastal Nature Hike|Nature hiking|Outdoor|Moderate|2-4 hours|Trail shoes, water|Dry and low wind|Group preferred|Low|Combines sea views, nature, and photography
Sunrise Hike|Nature hiking|Outdoor|Moderate|2-4 hours|Headlamp, trail shoes, water|Clear and stable|Group|Low|Strong landscape photography and quiet trails
Scenic Viewpoint Walk|Nature and scenery|Outdoor|Low-Moderate|45-120 min|Comfortable shoes, camera|Clear or partly cloudy|Solo or group|Free-Low|Short trip focused on views and photos
Botanical Garden Visit|Nature visit|Outdoor|Low|1-3 hours|Comfortable shoes, camera|Dry or mild|Solo or group|Low-Medium|Easy nature access with close-up photography
Birdwatching Walk|Nature observation|Outdoor|Low|1-3 hours|Binoculars optional, camera|Calm and dry|Solo or small group|Free-Low|Slow exploration and wildlife photography
Stargazing Trip|Nature and scenery|Outdoor|Low|1-3 hours|Blanket, warm layer, sky app|Clear night|Pair or group|Free-Low|A calm scenic activity away from city light
Ancient City Visit|History and travel|Outdoor|Low-Moderate|2-5 hours|Comfortable shoes, camera|Dry and mild|Solo or group|Low-Medium|History, walking, and architectural photography
Castle or Fortress Tour|History and travel|Indoor and outdoor|Moderate|1-3 hours|Comfortable shoes, camera|Most conditions|Solo or group|Low-Medium|Explores defensive architecture and viewpoints
Historic District Walk|History and travel|Outdoor|Low-Moderate|1-3 hours|Comfortable shoes, camera|Dry preferred|Solo or group|Free-Low|Street-level history, local food, and photography
Archaeology Museum Visit|Museum and history|Indoor|Low|1-3 hours|Admission optional|Any|Solo or group|Free-Medium|Detailed historical context without weather limits
Art Museum Visit|Museum and culture|Indoor|Low|1-3 hours|Admission optional|Any|Solo or group|Free-Medium|Visual discovery and a relaxed indoor day
Science Museum Visit|Museum and science|Indoor|Low|1-3 hours|Admission optional|Any|Solo or group|Free-Medium|Interactive exhibits and technology-focused exploration
Open-Air Museum Visit|Museum and history|Outdoor|Low-Moderate|2-4 hours|Comfortable shoes, camera|Dry and mild|Solo or group|Low-Medium|Combines museum content, walking, and photography
Museum and Cafe Day|Museum and social|Indoor|Low|2-4 hours|Admission and cafe budget|Any|Pair or group|Medium|Balances cultural exploration and relaxed conversation
Historical Photography Walk|Photography and history|Outdoor|Low-Moderate|1-3 hours|Phone or camera|Dry, soft light preferred|Solo or small group|Free-Low|Focuses directly on historical buildings and details
Nature Photography Walk|Photography and nature|Outdoor|Low|1-3 hours|Phone or camera|Dry or overcast|Solo or small group|Free-Low|Slow-paced search for landscapes, plants, and textures
Landscape Photography Trip|Photography and scenery|Outdoor|Low-Moderate|2-5 hours|Camera, water, tripod optional|Clear or dramatic clouds|Solo or group|Free-Medium|Destination-based photography at viewpoints
Golden Hour Photo Walk|Photography|Outdoor|Low|60-120 min|Phone or camera|Dry near sunrise or sunset|Solo or small group|Free|Uses soft light for city, nature, or historical scenes
Street Photography Walk|Photography and travel|Outdoor|Low-Moderate|1-3 hours|Phone or camera|Most daylight conditions|Solo or pair|Free|Turns casual city exploration into a creative challenge
Cycling by the Coast|Cycling and scenery|Outdoor|Moderate|60-180 min|Bike, helmet, water|Dry and low wind|Solo or group|Free-Low|Combines cycling, sea views, and photo stops
Park Cycling|Cycling|Outdoor|Moderate|45-120 min|Bike, helmet, water|Dry and mild|Solo or group|Free-Low|Easy recreational cycling away from heavy traffic
Historical Cycling Route|Cycling and history|Outdoor|Moderate|1-3 hours|Bike, helmet, route map|Dry and daylight|Group preferred|Free-Low|Connects several historical stops efficiently
Bike and Picnic Day|Cycling and picnic|Outdoor|Moderate|2-5 hours|Bike, helmet, food, water|Dry and mild|Group|Low|Mixes movement, food, nature, and rest
Okey Night|Table game|Indoor|Low|90-240 min|Okey set, table, snacks|Any|4 people|Low|A direct match for relaxed social competition
Okey Tournament|Table game|Indoor|Low|2-4 hours|Okey set, score sheet|Any|4-8 people|Low|Adds brackets and scores to a familiar game
Classic Card Game Night|Card game|Indoor|Low|60-180 min|Deck of cards, snacks|Any|2-6 people|Low|Flexible social entertainment with many game choices
Strategy Card Game Night|Card game|Indoor|Low|90-180 min|Strategy card game|Any|2-6 people|Low-Medium|More tactical and competitive than classic cards
Board Game Cafe Visit|Tabletop games|Indoor|Low|2-4 hours|Venue games|Any|2-6 people|Medium|Allows trying new games without buying them
Social Deduction Game Night|Party game|Indoor|Low|60-180 min|Game cards or app|Any|5-12 people|Free-Low|Conversation, bluffing, and group humor
Puzzle and Snacks Evening|Puzzle game|Indoor|Low|60-180 min|Jigsaw or puzzle game|Any|Solo or group|Low|A calm alternative to competitive games
League of Legends Session|PC gaming|Indoor|Low physical|45-150 min|PC, internet, headset|Any|Solo or team|Existing equipment|Competitive team strategy with familiar gameplay
Valorant Session|PC gaming|Indoor|Low physical|45-150 min|PC, internet, headset|Any|Solo or team|Existing equipment|Tactical team play and short match structure
Indie Game Discovery Night|PC gaming|Indoor|Low physical|60-180 min|PC or console|Any|Solo or group|Free-Medium|Explores creative shorter games outside major franchises
Co-op Game Night|PC gaming|Indoor|Low physical|90-240 min|PC or console, voice chat|Any|2-5 people|Free-Medium|Shared goals and social gaming without ranked pressure
Story-Driven Game Evening|PC gaming|Indoor|Low physical|90-240 min|PC or console|Any|Solo|Free-Medium|Relaxed immersion for days without outdoor energy
Competitive Gaming Night|PC gaming|Indoor|Low physical|90-240 min|PC, internet, headset|Any|Team|Existing equipment|A planned ranked session with breaks and a stop time
Local Multiplayer Night|Video games|Indoor|Low physical|60-180 min|Console or PC, controllers|Any|2-6 people|Free-Medium|Gaming in the same room with friends
Gaming Cafe Visit|PC gaming and social|Indoor|Low physical|2-4 hours|Venue equipment|Any|Group|Medium|Combines gaming with an in-person social plan
Indie Game and Discussion Night|PC gaming and social|Indoor|Low physical|90-180 min|PC or console|Any|2-5 people|Free-Medium|Play a short indie title and discuss its story or design
City Exploration Day|Travel and walking|Outdoor|Moderate|3-7 hours|Comfortable shoes, transit card, camera|Dry preferred|Solo or group|Low-Medium|Open-ended sightseeing, food, history, and photography
Neighborhood Discovery Walk|Travel and walking|Outdoor|Low-Moderate|1-3 hours|Comfortable shoes, camera|Most conditions|Solo or group|Free-Low|Finds overlooked streets, cafes, parks, and architecture
Train Day Trip|Travel|Indoor and outdoor|Low-Moderate|Half or full day|Tickets, small bag, camera|Most conditions|Solo or group|Medium|Easy access to a new town without driving
Food and Sightseeing Route|Travel and food|Outdoor|Low-Moderate|3-6 hours|Walking shoes, food budget|Dry preferred|Group|Medium|Combines exploring with planned local food stops
No-Plan Exploration Day|Travel and discovery|Outdoor|Low-Moderate|2-6 hours|Phone, transit card, camera|Dry preferred|Solo or group|Low-Medium|Flexible wandering guided by interesting places
Hammock or Park Rest|Rest and nature|Outdoor|Very low|45-150 min|Blanket or hammock, book optional|Dry and mild|Solo or pair|Free-Low|Rest outdoors without turning the day into a workout
Beach Rest Day|Rest and sea|Outdoor|Very low|2-5 hours|Towel, shade, water|Warm and calm|Solo or group|Free-Low|A low-effort sea day focused on relaxing
Movie and Rest Evening|Rest and entertainment|Indoor|Very low|2-4 hours|Screen, comfortable space|Any|Solo or group|Existing equipment|A deliberate recovery evening without planning pressure
Music and Power Nap|Rest|Indoor|Very low|30-90 min|Quiet room, alarm, music optional|Any|Solo|Free|Short recovery when energy is low
Sleep-In Morning|Rest|Home|Very low|1-3 extra hours|Quiet room|Any|Solo|Free|Intentional rest after a tiring week
Digital Detox Rest Hour|Rest|Indoor or outdoor|Very low|30-90 min|Comfortable place|Any|Solo|Free|A quiet break from games, messages, and screens
'@ | ConvertFrom-Csv -Delimiter '|'

$modes = @(
    @{Label='Easy Plan'; Guidance='Choose the shorter duration, keep preparation minimal, and leave room to stop early.'},
    @{Label='Full Plan'; Guidance='Use the full duration, include travel and breaks, and add one related stop or social element.'}
)

$lines=[System.Collections.Generic.List[string]]::new()
$lines.Add('# Personal Activity Library');$lines.Add('')
$lines.Add('A personalized activity catalog based on preferred sports, sea activities, nature, history, museums, picnics, tabletop games, PC gaming, cycling, travel, photography, and intentional rest.')
$lines.Add('');$lines.Add("- Core activities: $($activities.Count)");$lines.Add("- Plans: $($activities.Count*$modes.Count)")
$lines.Add('- Preference profile: basketball, swimming, hiking, historical places, museums, picnics, okey/cards, PC games, volleyball, badminton, cycling, exploring, resting, and nature/landscape/history photography')
$lines.Add('')
$index=1
foreach($activity in $activities){foreach($mode in $modes){
    $lines.Add("## $index. $($activity.Name) — $($mode.Label)");$lines.Add('')
    $lines.Add("- **Category:** $($activity.Category)");$lines.Add("- **Setting:** $($activity.Setting)")
    $lines.Add("- **Intensity:** $($activity.Intensity)");$lines.Add("- **Duration:** $($activity.Duration)")
    $lines.Add("- **Equipment:** $($activity.Equipment)");$lines.Add("- **Suitable conditions:** $($activity.Weather)")
    $lines.Add("- **Group:** $($activity.Group)");$lines.Add("- **Estimated cost:** $($activity.Cost)")
    $lines.Add('');$lines.Add('**Why it fits**');$lines.Add('');$lines.Add($activity.Why)
    $lines.Add('');$lines.Add('**Plan**');$lines.Add('');$lines.Add("$($mode.Guidance) Confirm weather, opening hours, transport, equipment, and group availability before starting.")
    $lines.Add('');$index++
}}

$resolved=[System.IO.Path]::GetFullPath($OutputPath)
[System.IO.File]::WriteAllLines($resolved,$lines,[System.Text.UTF8Encoding]::new($false))
Write-Output "Created: $resolved";Write-Output "Core activities: $($activities.Count)";Write-Output "Plans: $($activities.Count*$modes.Count)"
