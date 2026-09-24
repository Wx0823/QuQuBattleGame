# 斗蛐蛐手绘美术 v3

风格：精致手绘、略写实；甲壳、翅脉、天然骨质与旧陶器。使用内置 image_gen 生成，原始透明 PNG 保留，不覆盖数值配置。

## 已接入资源

- `crickets_side.png`：3×2 图集，6 个品种的侧面躯干。
- `crickets_top.png`：3×2 图集，同顺序的俯视躯干。
- `equipment.png`：3×2 图集，触须、牙齿、前躯、后躯、翅膀、尾巴。
- `effects.png`：2×2 图集，命中、格挡、扬尘、攻击弧光。
- `arena.png`：竞技场陶盆；桌面副本仍然透明无底。

角色图集按 `manifest.json` 映射到品种 ID；不从颜色推断品种。腿、触须、尾须是实时关节绘制，躯干贴图按呼吸缩放、背翅按鸣叫抬升，KO 保留手绘身体并翻转收腿，避免纯色腹甲覆盖贴图。装备贴图共用部位造型，品质通过彩色边框/底线表示，金色角标表示已穿戴。

资源只在首次使用时载入，透明遮罩用于定位主体边界，原图 alpha 保留。小尺寸绘制使用有限档位预缩小缓存，减少翅纹闪烁。新增品种/部位未配置贴图时回退到原有可配色绘制，不影响表格扩展。新增美术后更新图集和 manifest；重启游戏使缓存生效。

验证：`python art_checklist.py`、`python equipment_ui_checklist.py`；完整战斗回归请使用临时副本，避免覆盖存档。`python art_checklist.py --preview` 在 docs 生成品种、装备与战斗实机绘制预览。

以下是完整生成提示词。

## side

Use case: stylized-concept. Production game sprite atlas for a refined semi-realistic hand-painted Chinese fighting-cricket desktop game. Generate ONE transparent PNG atlas, exact 3 columns by 2 rows equal cells, SIX isolated cricket BODY sprites, one centered inside each cell with wide empty transparent gutters. All face RIGHT in strict SIDE profile, same scale and horizontal alignment. These are modular torso sprites for a skeletal animation system: draw ONLY connected abdomen with folded richly veined forewings, pronotum and head, tiny natural glossy black compound eye and small mandibles. ABSOLUTELY NO LEGS, NO ANTENNAE, NO tail filaments; those are animated separately in code. This is deliberately a limb-free insect torso sheet. No text, grid lines, ground, shadows, aura, glow, background or decoration. Entire canvas outside the six torsos must be genuinely alpha-transparent. Crisp clean cutout edges. Each torso fits within central 75% width and 55% height of its cell. Natural cricket proportions, small head, horizontal low abdomen, organic chitin, premium detailed painterly 2D game art, distinct restrained highlights readable at 100 pixels; not cartoon, not kawaii, no giant eyes, no human armor.
Cell order left to right then next row:
1 Chinese fighting cricket: olive green #6FA83C, walnut brown wing veins, balanced oval body.
2 Ironhead general cricket: slate gray #8A8F98, broad dark graphite pronotum, large angular head, compact tough body.
3 Gale cricket: jade green #4FA85F, slender tapered abdomen, narrow long wings, sleek small head.
4 Inkfang cricket: near black #3A3A3A, blue-black glossy wing edges, powerful dark mandibles, narrow aggressive head.
5 Oilgourd cricket: amber brown #B07A3A, rounded stout abdomen, lustrous chestnut head, copper wing veins.
6 Ironsand cricket: bronze earth brown #7A5C3A, thick robust pronotum, finely mottled ochre wing covers and bronze head.
The six are visibly different insect breeds, not simply recolored duplicates. Output atlas landscape 3:2.

## top

Production hand-painted game atlas, matching refined semi-realistic natural fighting crickets. EXACTLY six isolated LIMBLESS cricket TORSO sprites arranged in equal 3 columns x 2 rows on true transparent alpha. Strict orthographic TOP DOWN view looking directly at the BACK, NOT SIDE view, bilateral symmetry around horizontal body axis, heads face RIGHT in every cell. Each body horizontal, abdomen left, head right. Body includes only abdomen, richly veined paired folded wing covers, pronotum, small head with side-positioned black compound eyes and tiny mandibles. NO legs, NO antennae, NO tail filaments, all will be animated as separate layers. Broad translucent EMPTY gutters around every sprite. NO shadows, NO glow, NO halo, no labels or cell borders or painted background. Crisp alpha edges. Center every sprite in its cell and fit within 76% cell width, 50% cell height. Small-scale readability, nuanced chitin highlights, hand-painted premium game textures, realistic insect anatomy, no cartoon face.
Read left to right, top row: olive green balanced Chinese cricket; slate gray Ironhead cricket with notably broad graphite head and thick thorax; slender jade green Gale cricket with long narrow wing covers.
Bottom row: blue-black Inkfang cricket with dark hard mandibles and silver-blue edge highlights; stout amber-chestnut Oilgourd cricket with bulbous segmented abdomen; dark earth-bronze Ironsand cricket with thick squared pronotum and mottled ochre wings.
All six must have clearly distinct morphology. Transparent PNG landscape 3:2 atlas.

## equipment

Use case: stylized-concept. Production inventory icon atlas for a premium hand-painted semi-realistic Chinese fighting-cricket game. EXACT 3 columns x 2 rows grid of SIX separate isolated collectible organic insect equipment illustrations, one centered per equal cell, ample transparent margins, no grid or letters. True alpha-transparent background, no ground, no shadows, no fog, no glow. Elegant warm bronze/gold and olive chitin, ivory details, engraved natural ridges and specular edges, striking simple silhouette readable at 40px, beautiful polished 2D RPG loot icon quality, not line art, not minimal symbols. No actual crickets or heads, only equipment parts.
Top left: a matched pair of gracefully curved long segmented cricket antennae rooted in ornate bronze chitin sockets.
Top middle: two powerful curved ivory-and-obsidian cricket mandibles, sharp interlocking cutting edges, compact symmetrical trophy silhouette.
Top right: a domed broad cricket pronotum breastplate, organic bronze armor shell, raised central ridge and scalloped lower edge.
Bottom left: a powerful jointed cricket hind-leg assembly, thick green-bronze muscular femur, serrated shin bent into a compact angular shape, no whole insect.
Bottom middle: a beautifully veined pair of folded translucent amber cricket wings arranged as a tapered fan.
Bottom right: paired long pointed cricket tail cerci with a segmented chitin tail base, elegant forked shape.
Every object fits entirely in central 65% of each cell and does not touch cell edges. No card frames, quality badges, labels, text, numerals, watermark or decorative backgrounds. Landscape 3:2 atlas.

## effects

Production 2D game VFX sprite atlas for a refined hand-painted semi-realistic Chinese cricket fighting game. Four isolated effects in an EXACT 2x2 equal-cell grid, true alpha transparent everywhere outside effects, ample gutters. Top left: compact ivory-and-amber impact burst, sharp radial slivers, tiny flying gold sparks, no smoke. Top right: elegant curved teal-and-pale-jade defensive arc, thin translucent shield crescent, not a solid disc, open center. Bottom left: small softly billowing warm beige dust puff with granular earth fragments, hand-painted natural dust. Bottom right: sweeping ivory-bronze attack slash arc, tapered two strokes and tiny sparks, open transparent center. All readable at 60 pixels, premium restrained painted action effects, no icons, no symbols, no lettering, no frames, no black squares, no scenic background. Each effect entirely within central 75% of own cell. Square atlas.

## arena

Use case: stylized-concept. A production game environment sprite: ONE empty traditional Chinese cricket fighting ceramic bowl seen in strict orthographic top-down view, perfectly circular rim. Premium hand-painted semi-realistic 2D game art matching natural cricket sprites and bronze equipment icons. Warm aged charcoal-brown earthenware thick rim with subtle handmade incised concentric bands, inner wall smooth warm umber, broad flat pale sand clay floor with restrained fine mineral grain, tiny worn scratches and subtle diffuse shading. Playable interior must be flat, quiet, spacious, unobstructed, readable, approximately 85% of diameter. No crickets, no creatures, no rocks, no plants, no writing, no glyphs, no tools, no UI. Whole bowl centered with 6% transparent margin outside circular rim, true alpha transparent background. No table or outside environment. Polished painterly texture, no heavy vignette or dramatic shadows. Square output.

## v0.6.11 待机草地

- 素材：`idle_grass.png`，使用内置 image_gen 工具生成，保留原始透明通道；游戏运行时通过既有 sprite 入口裁掉透明外边，不修改源图。
- 用途：蛐蛐脚下的草地台座，地块内部承载装备/副本按钮；等级与经验位于头顶横排。
- 四肢继续使用可动画骨架：颜色采样身体贴图，股节叠加同源甲壳纹理，胫节增加节纹与关节体积，触须渐细并呈分节明暗。避免重新引入统一浅棕色粗线。
- 生成提示词：

Create one production game sprite, transparent RGBA background, no lettering no insects no UI buttons. A long low horizontal floating cutaway patch of meadow turf, front/side view with just a slight view of the grassy top, aspect ratio about 5:1. Precise silhouette: flat walkable top rim, short fine mossy olive-green grass along entire top, very shallow earthy brown soil thickness beneath with a few small roots and warm mineral grains. The soil front face must be dark, calm and mostly uncluttered in its center so two UI buttons can later overlay it. Mature delicate hand-painted natural history illustration, slightly realistic, intricate fine brush texture, warm muted bronze and moss colors, soft upper-left light. Isolated on genuinely transparent background with ample transparent padding, no drop-shadow rectangle, no scenery or sky. This will sit beneath a detailed bronze-black cricket in a desktop pet game. Flat horizontal layout not an isometric cube, not cartoon, no bright neon greens. Output crisp high resolution.

## v0.6.12 草地修改

用户要求草色更绿、更浓密，土层为平整纯色，不保留孔洞、根须、石块等写实纹理。使用内置 image_gen 编辑原图，替换 `idle_grass.png`；透明背景与现有按钮布局保留。

最终提示词：
Edit the provided game platform asset. Keep the same long horizontal platform composition and transparent background, no characters no text no buttons. Completely replace the muddy rocky soil underside with a perfectly smooth SINGLE SOLID COLOR muted dark brown (#65503C) shape, flat 2D fill with a clean straight bottom and softly rounded bottom corners. Absolutely NO holes, pores, stones, roots, speckles, texture, shading, photorealism or uneven scallops in the brown part. The brown front panel is featureless and calming, suitable for overlaying UI buttons. On top, replace the dry yellow olive grass with a lush dense continuous carpet of fresh clearly GREEN grass, rich leaf greens #4F922E and #76B548, thicker and fuller than original, many fine overlapping blades, no sparse bare places and no yellow brown cast. Pleasant stylized hand-painted game grass over flat minimal soil; no realistic dirt. Maintain the original occupied bounds and low wide silhouette approximately. Genuinely transparent alpha background, do not draw checkerboard pattern. This is a direct replacement for a desktop pet grass dock.

透明通道修正提示词（最终采用此轮输出，RGBA alpha 范围 0~255）：
Keep exactly this lush green grass and clean smooth brown platform, preserving colors, silhouette and all asset details. REMOVE THE BLACK BACKGROUND entirely and export as transparent RGBA PNG with actual alpha=0 outside the platform. This is a game sprite for overlaying a desktop, so there must be genuine transparency around it, not black, not white, not checkerboard, not simulated transparency. Brown region remains flat single uniform brown with no texture and no gradient. No new objects no text. Only correct the transparent background.
