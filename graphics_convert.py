"""Full-page vector, CAD and high precision raster adapters."""
from localization import localize
from pathlib import Path
import gzip
import tempfile
import os
import shutil
import rawpy
import numpy as np
import pymupdf
from PIL import Image

from capabilities import input_extension, extension
from external_tools import locate,run_tool,ROOT,libreoffice
from transactions import publish
from pdf_convert import convert_pdf

RAW_EXTENSIONS=set('3fr arw cr2 cr3 crw dcr dng erf mos mrw nef orf pef raf raw rw2 x3f'.split())
DRAW_FILTERS={'cdr':'Corel Draw Document','vsd':'Visio Document','pub':'Publisher Document','odg':'draw8','odd':'draw8'}


def dwg_tool(name):
    for path in [ROOT/('libredwg/'+name+'.exe'),ROOT/('third-party/libredwg/'+name+'.exe')]:
        if path.is_file():return path
    raise ValueError(localize('Не знайдено LibreDWG.'))


def read_dxf(path):
    import ezdxf
    # LibreDWG can emit a zero handle on a non-geometric ENDBLK marker.
    # Assign an unused identity only to that marker, never alter geometry.
    data=Path(path).read_bytes()
    lines=data.splitlines();changed=False
    current=b''
    handles=[int(lines[i+1].strip(),16) for i in range(0,len(lines)-1,2) if lines[i].strip() in {b'5',b'105'} and all(c in b'0123456789abcdefABCDEF' for c in lines[i+1].strip())]
    next_handle=max(handles+[0])+1
    for index in range(0,len(lines)-3,2):
        if lines[index].strip()==b'0':current=lines[index+1].strip()
        if current==b'ENDBLK' and lines[index].strip()==b'5' and lines[index+1].strip()==b'0':
            lines[index+1]=format(next_handle,'X').encode();next_handle+=1;changed=True
        if lines[index].strip()==b'9' and lines[index+1].strip()==b'$HANDSEED' and lines[index+2].strip()==b'5' and lines[index+3].strip()==b'0':
            lines[index+3]=b'10000000';changed=True
    if changed:Path(path).write_bytes(b'\n'.join(lines)+b'\n')
    document=ezdxf.readfile(path)
    if document.audit().errors:raise ValueError(localize('Креслення містить невиправні помилки.'))
    return document


def as_pdf(source,destination,work):
    suffix=input_extension(source)
    if suffix in {'dwf','dwfx'}:
        from dwf_convert import render
        render(source,destination,work)
    elif suffix in {'sk','sk1'}:
        from sk_convert import convert
        convert(source,'pdf',destination,work)
    elif suffix in DRAW_FILTERS or suffix in {'cgm','sda'}:
        libreoffice(source,'pdf',destination,work/'office',DRAW_FILTERS.get(suffix),family='draw')
    elif suffix in {'dxf','dwg'}:
        dxf=source
        if suffix=='dwg':
            dxf=work/'drawing.dxf'
            run_tool([dwg_tool('dwg2dxf'),'-y','-o',dxf,source],work)
        else:
            dxf=work/'drawing.dxf';shutil.copyfile(source,dxf)
        import ezdxf
        from ezdxf.addons.drawing import Frontend,RenderContext,layout
        from ezdxf.addons.drawing.svg import SVGBackend
        drawing=read_dxf(dxf)
        unsupported={'3DSOLID','REGION','BODY','ACAD_PROXY_ENTITY','OLE2FRAME','IMAGE','UNDERLAY','PDFUNDERLAY'}
        bad=sorted({e.dxftype() for e in drawing.modelspace() if e.dxftype() in unsupported})
        if bad:raise ValueError(localize('Це креслення містить непідтримувані об’єкти: ')+', '.join(bad))
        backend=SVGBackend()
        Frontend(RenderContext(drawing),backend).draw_layout(drawing.modelspace(),finalize=True)
        svg=work/'drawing.svg';svg.write_text(backend.get_string(layout.Page(0,0)),encoding='utf-8')
        run_tool([locate('inkscape'),svg,'--export-type=pdf','--export-filename='+str(destination)],work)
    elif suffix in {'svg','svgz','emf','wmf','ai','eps','ps'}:
        native=source
        if suffix=='svgz':
            native=work/'input.svg'
            with gzip.open(source,'rb') as stream:native.write_bytes(stream.read(200_000_001))
            if native.stat().st_size>200_000_000:raise ValueError(localize('SVG завеликий.'))
        if source.read_bytes()[:4]==b'%PDF':
            with pymupdf.open(source) as document:document.save(destination)
        elif suffix in {'ai','eps','ps'}:
            ghostscript=next((p for p in [ROOT/'ghostscript/bin/gswin64c.exe',ROOT/'third-party/ghostscript/bin/gswin64c.exe'] if p.is_file()),None)
            if not ghostscript:raise ValueError(localize('Не знайдено Ghostscript.'))
            run_tool([ghostscript,'-dSAFER','-dBATCH','-dNOPAUSE','-sDEVICE=pdfwrite',
                      '-dAutoRotatePages=/None','-dDownsampleColorImages=false','-dDownsampleGrayImages=false',
                      '-dDownsampleMonoImages=false','-dColorImageFilter=/FlateEncode','-dGrayImageFilter=/FlateEncode',
                      '-sOutputFile='+str(destination),'-f',source],work)
        else:
            run_tool([locate('inkscape'),native,'--export-type=pdf','--export-filename='+str(destination)],work)
    elif suffix=='xps':
        with pymupdf.open(source) as document:destination.write_bytes(document.convert_to_pdf())
    else:
        # PSB/XCF compositing uses all layers; no arbitrary first-layer export.
        run_tool([locate('magick'),source,'-background','none','-layers','merge','-compress','Zip',destination],work)
    with pymupdf.open(destination) as document:
        if not document.is_pdf or not len(document):raise ValueError(localize('Конвертер не створив повний PDF.'))


def convert_graphics(source,target,overwrite=False):
    source=Path(source).absolute();destination=source.with_suffix('.'+extension(target))
    if source==destination:raise ValueError(localize('Файл уже має цей формат.'))
    with tempfile.TemporaryDirectory(prefix='.convert-graphics-',dir=source.parent) as directory:
        work=Path(directory);suffix=input_extension(source)
        if (suffix,target) in {('svg','svgz'),('svgz','svg')}:
            data=source.read_bytes()
            if suffix=='svgz':
                with gzip.open(source,'rb') as stream:data=stream.read(200_000_001)
                if len(data)>200_000_000:raise ValueError(localize('SVG завеликий.'))
            else:data=gzip.compress(data,compresslevel=9)
            staged=work/destination.name;staged.write_bytes(data)
            return publish([(staged,destination)],overwrite)
        if target in {'sk','sk1','cdr','cgm'}:
            from sk_convert import convert
            if suffix in {'svg','sk','sk1','cdr','cgm','wmf'}:
                staged=work/destination.name;convert(source,target,staged,work/'uniconvertor')
                return publish([(staged,destination)],overwrite)
            pdf=work/'source.pdf';as_pdf(source,pdf,work)
            files=[]
            with pymupdf.open(pdf) as document:
                for index,page in enumerate(document):
                    svg=work/('page-'+str(index)+'.svg');svg.write_text(page.get_svg_image(text_as_path=True),encoding='utf-8')
                    staged=work/(source.stem+(f'_{index+1}' if index else '')+'.'+target)
                    convert(svg,target,staged,work/('uc-'+str(index)));files.append(staged)
            return publish([(p,source.parent/p.name) for p in files],overwrite)
        if target in {'dwg','dxf'} and suffix in {'dwg','dxf'}:
            staged=work/destination.name
            tool='dwg2dxf' if target=='dxf' else 'dxf2dwg'
            run_tool([dwg_tool(tool),'-y','-o',staged,source],work)
            if target=='dxf':
                read_dxf(staged)
            else:
                if not staged.read_bytes().startswith(b'AC10'):raise ValueError(localize('Невірний вихідний DWG.'))
            return publish([(staged,destination)],overwrite)
        if suffix in RAW_EXTENSIONS:
            # Demosaic at native dimensions, camera WB and 16-bit sRGB.
            with rawpy.imread(str(source)) as raw:
                pixels=raw.postprocess(output_bps=16,use_camera_wb=True,no_auto_bright=True,gamma=(2.4,12.92),output_color=rawpy.ColorSpace.sRGB)
            import imagecodecs
            tiff=work/'raw.tiff';tiff.write_bytes(imagecodecs.tiff_encode(pixels,compression='deflate'))
            staged=work/destination.name
            profile=Path(locate('magick')).parent/'sRGB.icc'
            if target=='pdf':
                from precision import save_rgb16_pdf
                save_rgb16_pdf(pixels.astype('>u2').tobytes(),(pixels.shape[1],pixels.shape[0]),staged,profile.read_bytes())
                return publish([(staged,destination)],overwrite)
            options=['-quality','100']
            if target=='jpg':options+=['-sampling-factor','4:4:4']
            if target in {'png','tiff','psd','psb'}:options+=['-depth','16','-compress','Zip']
            if target=='png':options+=['-define','png:bit-depth=16','-define','png:color-type=2']
            if target=='webp':options+=['-define','webp:lossless=true']
            if target=='avif':options+=['-depth','12','-define','heic:lossless=true','-define','heic:chroma=444']
            options+=['-set','colorspace','sRGB','-profile',profile]
            run_tool([locate('magick'),tiff,*options,staged],work)
            return publish([(staged,destination)],overwrite)
        if target in {'icns','psb'}:
            staged=work/destination.name
            if target=='icns':
                with Image.open(source) as image:image.save(staged,format='ICNS')
            else:run_tool([locate('magick'),source,'-compress','Zip',staged],work)
            return publish([(staged,destination)],overwrite)
        pdf=work/(source.stem+'.pdf');as_pdf(source,pdf,work)
        staged=[pdf] if target=='pdf' else convert_pdf(pdf,target)
        return publish([(p,source.parent/p.name) for p in staged],overwrite)


def planned_outputs(source,target):
    source=Path(source).absolute()
    from pdf_convert import PAGE_FORMATS
    direct_native=target in {'sk','sk1','cdr','cgm'} and input_extension(source) in {'svg','sk','sk1','cdr','cgm','wmf'}
    if direct_native or input_extension(source) in RAW_EXTENSIONS or target in {'icns','psb','dwg','dxf','pdf'} or target not in PAGE_FORMATS:
        return [source.with_suffix('.'+extension(target))]
    with tempfile.TemporaryDirectory(prefix='.convert-plan-',dir=source.parent) as directory:
        work=Path(directory);pdf=work/'source.pdf';as_pdf(source,pdf,work)
        with pymupdf.open(pdf) as document:
            return [source.with_name(source.stem+(f'_{i+1}' if i else '')+'.'+extension(target)) for i in range(len(document))]
