import json
import os
import requests
from lxml import etree
import time

header = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36'

SleepTime = 2  # second
RetryTime = 3


class Page:
    def __init__(self, idx: int = 0, url: str = "", head: str = ""):
        self.header = head
        self.text = ""
        self.id = idx
        self.url = url

    # 定义接口：SearchFunc输入为html: Response，输出为二元组(内容，ok)
    def GetPage(self, WebClass) -> bool:
        ok = False
        url = WebClass.GenerateUrl(self.url)

        for i in range(RetryTime):
            if ok: break
            time.sleep(SleepTime)
            print("parse %s ··········" % self.header, end=" ")
            try:
                html = requests.get(url, header)
            except requests.exceptions.ConnectionError:
                print("\t fail  parse %s %d/%d " % (self.header, i, RetryTime))
                continue
            text, SearchOK = WebClass.SearchNovel(html)
            if not SearchOK:
                raise RuntimeError("Search Error")

            self.text = text
            ok = True
        if not ok:
            print("fail Parse %s, will retry later" % self.header)
        else:
            print("SUCCESS")
        return ok

    def GenerateDic(self):
        return {"header": self.header, "text": self.text, "id": self.id, "url": self.url}

    def InitFromDic(self, dic):
        self.header = dic["header"]
        self.text = dic["text"]
        self.id = dic["id"]
        self.url = dic["url"]


class Novel:
    def __init__(self, WebClass, BreakPath: str = ""):
        self.pages = {}
        self.ok = []

        self.MenuURL = WebClass.NovelMenuUrl
        self.header = ""

        self.WebClass = WebClass
        self.CheckWebClass()

        self.bkpF = None
        self.bkpFName = ""

        self.BreakPath = BreakPath

    def CheckWebClass(self):
        if not hasattr(self.WebClass, "SearchNovelHeader"):
            raise AssertionError("dont have SearchNovelHeader")
        elif not hasattr(self.WebClass, "SearchURLs"):
            raise AssertionError("dont have SearchURLs")
        elif not hasattr(self.WebClass, "SearchNovel"):
            raise AssertionError("dont have SearchNovel")
        elif not hasattr(self.WebClass, "GenerateUrl"):
            raise AssertionError("dont have GenerateUrl")

    def GetMenuPage(self) -> requests.Response:
        html = requests.get(self.MenuURL, header)
        return html

    # 定义接口：SearchHeader输入为requests.Response,输出二元组(标题，ok)
    def GetHeader(self, MenuData: requests.Response) -> bool:
        self.header, ok = self.WebClass.SearchNovelHeader(MenuData)
        if ok:
            return True
        else:
            return False

    # 定义接口：SearchURLs输入为requests.Response,输出二元组((URLs,标题)，ok)
    def GetNovelURLs(self, MenuData: requests.Response) -> bool:
        URLs, ok = self.WebClass.SearchURLs(MenuData)
        if not ok:
            return False

        # 从前往后为每一个URL进行编号，录入到pages里，同时初始化ok
        self.ok = [False] * len(URLs)
        for idx, each in enumerate(URLs):
            self.pages[idx] = Page(idx, url=each[0], head=each[1])
        return True

    def IsCompelete(self) -> bool:
        for each in self.ok:
            if not each:
                return False
        return True if self.ok else False

    def Run(self):
        if self.BreakPath == "":
            # 若是不需要读取断点文件，就直接爬取目录
            MenuPage = self.GetMenuPage()
            ok = self.GetHeader(MenuPage)
            if not ok:
                raise RuntimeError("Get Header Error")
            print("begin %s" % self.header)

            ok = self.GetNovelURLs(MenuPage)
            if not ok:
                raise RuntimeError("Get URL Error")

            # 生成此时需要的断点文件，防止后续中断
            self.bkpFName = "%s_%s_breakpoint.json" % (self.header, time.asctime(time.localtime(time.time())))
            self.bkpFName = self.bkpFName.replace(" ", "_").replace(":", "_")
            self.bkpF = open(self.bkpFName, "a+", encoding="utf-8")
        else:
            # 若是需要读入断点文件
            print("read from json: %s" % self.BreakPath)
            self.bkpF = open(self.BreakPath, "r", encoding="utf-8")
            dic = json.load(self.bkpF)
            self.bkpF.close()
            # 对读取的数据进行处理
            self.MenuURL = dic["MenuURL"]
            self.header = dic["header"]
            self.ok = [False] * len(dic["pages"])

            for key, each in dic["pages"].items():
                self.pages[each["page"]["id"]] = Page()
                self.pages[each["page"]["id"]].InitFromDic(each["page"])
                self.ok[each["page"]["id"]] = each["ok"]
            print("read complete, continue %s(%s)" % (self.header, self.MenuURL))
            # 处理完成，清空这个文件，要是中断了继续写这个
            self.bkpF = open(self.BreakPath, "w", encoding="utf-8")
            self.bkpFName = self.BreakPath

        queue = []
        for idx, each in enumerate(self.ok):
            if not each:
                queue.append(idx)

        while queue:
            idx = queue.pop(0)

            if self.pages[idx].GetPage(WebClass=self.WebClass):
                self.ok[idx] = True
            else:
                queue.append(idx)
        self.SaveFile()
        print("%s complete" % self.header)

    def SaveFile(self):
        print("begin save txt")
        f = open("%s.txt" % self.header, 'a+', encoding='utf-8')
        l = len(self.ok)
        for idx in range(l):
            f.write(self.pages[idx].header + "\n\n")
            f.write(self.pages[idx].text + "\n")
        f.close()
        print("exit program")

    def SaveBreakPoint(self):
        pages = {}
        dic = {}
        for idx, each in enumerate(self.ok):
            pages[idx] = {"ok": each, "page": self.pages[idx].GenerateDic()}
        dic["pages"] = pages
        dic["MenuURL"] = self.MenuURL
        dic["header"] = self.header

        self.bkpF.write(json.dumps(dic))
        self.bkpF.close()

    def __del__(self):
        if not self.ok and self.bkpF is None:
            # 若ok为空数组，同时没有生成json文件，则表明没有开始爬取，直接返回，
            return
        elif self.IsCompelete():
            # 若是爬取成功完成，则说明已存入文件，需要删除json文件
            self.bkpF.close()
            os.remove(self.bkpFName)
        else:
            # 存储断点
            self.SaveBreakPoint()


class WebClassSample:
    def __init__(self, Domain="", NovelMenuURL="", CharSet=""):
        self.Domain = Domain
        self.NovelMenuUrl = NovelMenuURL
        self.CharSet = CharSet

    def SearchNovelHeader(self, MenudData: requests.Response):
        pass

    def SearchURLs(self, MenudData: requests.Response):
        pass

    def SearchNovel(self, PageData: requests.Response):
        pass

    def GenerateUrl(self, url: str) -> str:
        pass


# www.iwurexs.com
class iwurexs(WebClassSample):
    def __init__(self, Domain, NovelMenuURL, CharSet):
        super(iwurexs, self).__init__(Domain=Domain, NovelMenuURL=NovelMenuURL, CharSet=CharSet)

    def SearchNovelHeader(self, MenudData: requests.Response):
        root = etree.HTML(MenudData.content.decode(self.CharSet))
        head = root.xpath("/html/body/div[5]/div/div[1]/div/div/div[2]/h1/text()")[0]
        return head, True

    def SearchURLs(self, MenudData: requests.Response):
        root = etree.HTML(MenudData.content.decode(self.CharSet))
        urls = root.xpath("/html/body/div[5]/div/div[3]/div[2]/ul//li/a/@href")
        name = root.xpath("/html/body/div[5]/div/div[3]/div[2]/ul//li/a/text()")
        return list(zip(urls, name)), True

    def SearchNovel(self, PageData: requests.Response):
        root = etree.HTML(PageData.content.decode(self.CharSet))
        text = root.xpath("//*[@id='content']/text()")
        text[0] = text[0].replace(" ", "")
        page = "\n".join(text[:-1])
        page = page.replace('\xa0', "")
        return page, True

    def GenerateUrl(self, url: str) -> str:
        return self.NovelMenuUrl + url


if __name__ == "__main__":
    web = iwurexs("https://www.iwurexs.com/", "https://www.iwurexs.com/read/587/", "utf-8")
    novel = Novel(web, BreakPath="斗破苍穹_Wed_Jul_20_17_58_49_2022_breakpoint.json")
    # novel = Novel(web)

    novel.Run()
