"""Opt-in authoring measurements using the same Pango Text as the renderer.

No schema/default-runtime changes. Callers own cache directories and semantic
containers; text lengths are never used as a substitute for rendered extents.
"""
from functools import lru_cache

@lru_cache(maxsize=4096)
def measure_text(text, font_size=27, font='Microsoft YaHei', max_width=10):
    from manim import Text
    mob=Text(str(text),font=font,font_size=font_size,color='#FFFFFF')
    if mob.width>max_width:mob.scale(max_width/mob.width)
    return float(mob.width),float(mob.height)

@lru_cache(maxsize=32)
def decimal_center_offset(font_size=27,font='Microsoft YaHei'):
    from manim import Text
    reference=Text('0.0',font=font,font_size=font_size,color='#FFFFFF')
    return float(reference[1].get_center()[1]-reference[0].get_center()[1])

def token_row(tokens, *, x=0, y=0, font_size=27, gap=.12, max_span=12,
              font='Microsoft YaHei', max_width=10):
    dimensions=[measure_text(t,font_size,font,max_width) for t in tokens]
    span=sum(w for w,h in dimensions)+gap*max(0,len(tokens)-1)
    if span>max_span+1e-8:
        raise ValueError(f'Measured glyph row exceeds semantic container: {span:.3f}>{max_span}: {tokens!r}')
    cursor=x-span/2;positions=[]
    for token,(width,height) in zip(tokens,dimensions):
        dy=decimal_center_offset(font_size,font) if token=='.' else 0
        positions.append([round(cursor+width/2,8),round(y+dy,8)])
        cursor+=width+gap
    return positions

def validate_text_state(objects, *, containers=None, font='Microsoft YaHei'):
    """Measure a caller-provided *visible stable* state, never hidden futures.

    containers maps semantic formula_group to [left,right,bottom,top]. Findings
    are evidence for the director, not an automatic runtime mutation or guard.
    """
    boxes=[];issues=[]
    for o in objects:
        if o.get('type')!='text':continue
        w,h=measure_text(o['text'],o.get('font_size',28),font,o.get('max_width',9))
        x,y=o['position'];b=[x-w/2,x+w/2,y-h/2,y+h/2]
        boxes.append({'id':o['id'],'text':o['text'],'bounds':b,'group':o.get('formula_group')})
        container=(containers or {}).get(o.get('formula_group'))
        if container and (b[0]<container[0] or b[1]>container[1] or b[2]<container[2] or b[3]>container[3]):
            issues.append({'type':'semantic_container_overflow','id':o['id'],'bounds':b,'container':container})
    for i,a in enumerate(boxes):
        for b in boxes[i+1:]:
            aa,bb=a['bounds'],b['bounds']
            if min(aa[1],bb[1])-max(aa[0],bb[0])>1e-6 and min(aa[3],bb[3])-max(aa[2],bb[2])>1e-6:
                issues.append({'type':'glyph_overlap','ids':[a['id'],b['id']],'bounds':[aa,bb]})
    return {'boxes':boxes,'issues':issues,'passed':not issues,'measurement':'native Pango/Manim Text; not pixel/animation QA'}
